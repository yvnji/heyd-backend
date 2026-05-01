import json
import os

import shortuuid
from boto3.dynamodb.conditions import Key

import const
from lib import client
from lib import time
from lib.decorator import preprocessing_cursor
from service import chatroom as chatroom_module
from service import reaction as reaction_module
from thirdparty import dynamodb


@preprocessing_cursor
def activate_content_chatroom(
    chatroom_id: int,
    connect_id: int,
    user_id: int,
    activate: bool,
    cursor: object = None
) -> None:
    """채팅방 컨텐츠 활성화 (입장)

    :param chatroom_id: chatroom ID
    :param connect_id: connect ID
    :param user_id: 사용자 ID
    :param activate: 활성화 / 비활성화
    :param cursor: pymysql.connect().cursor()
    """
    now_at = time.now()

    # 채팅방 활성화
    if activate:
        query = """
        INSERT INTO `content_chatroom_active` (user_id, connect_id)
        VALUES (%s, %s)
        ON DUPLICATE KEY UPDATE
            active = 1,
            created_at = %s,
            start_at = %s,
            latest_at = %s
        RETURNING id
        """
        cursor.execute(query, (user_id, connect_id, now_at, now_at, now_at))
        chatroom_active = cursor.fetchone()
        start_at = time.totimestamp(now_at)

        # 캐릭터 최초 메세지 전송
        chatroom_module.send_first_chat(
            chatroom_id,
            chatroom_active["id"],
            start_at,
            cursor=cursor
        )

    # 채팅방 비활성화
    else:
        query = """
        UPDATE `content_chatroom_active`
        SET
            active = 0
        WHERE
            user_id = %s
            AND connect_id = %s
        """
        cursor.execute(query, (user_id, connect_id))


@preprocessing_cursor
def connect_content_chatroom(content_id: int, chatroom_id: int, cursor: object = None) -> int:
    """채팅 컨텐츠에 채팅방 연결

    :param content_id: 컨텐츠 ID
    :param chatroom_id: 채팅방 ID
    :param cursor: pymysql.connect().cursor()

    :return: 생성된 연결 ID
    """
    query = """
    INSERT INTO `content_connect` (content_id, chatroom_id)
    VALUES (%s, %s)
    RETURNING id
    """
    cursor.execute(query, (content_id, chatroom_id))
    return cursor.fetchone()["id"]


@preprocessing_cursor
def create_content(
    title: str,
    description: str,
    thumbnail_id: int,
    content_type: str,
    rating: str,
    user_id: str,
    cursor: object = None
) -> int:
    """새 컨텐츠 생성

    :param title: 제목
    :param description: 설명
    :param thumbnail_id: 썸네일 ID
    :param content_type: 컨텐츠 타입
    :param rating: 컨텐츠 등급
    :param user_id: 사용자 ID
    :param cursor: pymysql.connect().cursor()

    :return: 생성된 컨텐츠 ID
    """
    query = """
    INSERT INTO `content` (title, description, thumbnail_id, type, rating, creator_id)
    VALUES (%s, %s, %s, %s, %s, %s)
    RETURNING id
    """
    cursor.execute(query, (title, description, thumbnail_id, content_type, rating, user_id))
    return cursor.fetchone()["id"]


@preprocessing_cursor
def deactivate_content(content_id: int, cursor: object = None) -> None:
    """컨텐츠 비활성화

    :param content_id: 컨텐츠 ID
    :param cursor: pymysql.connect().cursor()
    """
    query = f"""
    UPDATE `content`
    SET active = 0
    WHERE id = {content_id}
    """
    cursor.execute(query)


@preprocessing_cursor
def disconnect_content_chatroom(content_id: int, chatroom_id: int = None, cursor: object = None) -> list:
    """채팅 컨텐츠에 채팅방 연결 해제

    :param content_id: 컨텐츠 ID
    :param chatroom_id: 채팅방 ID
    :param cursor: pymysql.connect().cursor()

    :return: 해제된 연결 ID 리스트
        [int, ...]
    """
    query_where = []
    query_where.append(f"content_id = {content_id}")
    if chatroom_id:
        query_where.append(f"chatroom_id = {chatroom_id}")
    query_where = " AND ".join(query_where)
    query = f"""
    SELECT id
    FROM `content_connect`
    WHERE {query_where}
    """
    cursor.execute(query)
    connect_ids = cursor.fetchall()
    connect_ids = [c["id"] for c in connect_ids] if connect_ids else []

    for cid in connect_ids:
        query = f"""
        UPDATE `content_connect`
        SET active = 0
        WHERE id = {cid}
        """
        cursor.execute(query)
    return connect_ids


@preprocessing_cursor
def get_background(background_id: str, cursor: object = None) -> dict:
    """배경화면 조회"""
    query = f"SELECT * FROM `background` WHERE id = '{background_id}'"
    cursor.execute(query)
    return cursor.fetchone()


@preprocessing_cursor
def get_bgm(bgm_id: str, cursor: object = None) -> dict:
    """배경음악 조회"""
    query = f"SELECT * FROM `bgm` WHERE id = '{bgm_id}'"
    cursor.execute(query)
    return cursor.fetchone()


@preprocessing_cursor
def get_content(content_id: int, cursor: object = None) -> dict:
    """컨텐츠 기본 조회

    :param content_id: 컨텐츠 ID
    :param cursor: pymysql.connect().cursor()

    :return
        {}
    """
    try:
        content_id = int(content_id)
    except ValueError:
        return {}

    query = f"""
    SELECT
        thumbnail_id,
        created_at,
        title,
        description,
        type,
        creator_id,
        category,
        rating
    FROM `content`
    WHERE
        active = 1
        AND id = {content_id}
    """
    cursor.execute(query)
    data = cursor.fetchone()
    if data:
        data["created_at"] = time.totimestamp(data["created_at"])
    else:
        data = {}
    return data


@preprocessing_cursor
def get_content_chatroom_detail(content_id: int, email: str = None, user_id: int = None, cursor: object = None) -> dict:
    """채팅방 컨텐츠 상세 조회

    :param content_id: 컨텐츠 ID
    :param email: 호출자 email
    :param user_id: 호출자 ID
    :param cursor: pymysql.connect().cursor()

    :return
        {
            'id': int,   # content id
            'thumbnail_file_path': str,
            'thumbnail_id': int,
            'created_at': Decimal,
            'title': str,
            'description': str,
            'type': str,   # e.g. 'chatroom'
            'rating': str,   # 연령 등급 ('G': 모든 연령, '18+': 성인 등급)
            'is_liked': bool,   # 사용자 좋아요 유무
            'like_count': int,   # 좋아요 수
            'user_count': int,   # 컨텐츠 이용자 수
            'tags': list,
            'creator_nickname': str,
            'creator_email': str,
            'user_chat_count': int,   # 이용자들의 총 채팅 수 (AI 채팅 제외)
            'emojis': [
                {
                    'emoji_id': int,
                    'emoji_type': str,   # 이모지 이름
                    'count': int,   # 해당 이모지 등록한 수,
                    'is_clicked': bool   # 호출자 이모지 등록 확인
                },
                ...
            ],
            'chatroom': {
                'id': int,
                'title': str,
                'background_name': str,
                'creator_nickname': str,
                'creator_email': str,
                'background_file_path': str,
                'background_id': int,
                'bgm_file_path': str,
                'bgm_id': int,
                'bgm_name': str,
                'characters': [
                    {
                        'character_id': str,
                        'created_time': Decimal,
                        'character_name': str,
                        'description': str,
                        'email': str,   # 생성자 email
                        'type': str   # 캐릭터 타입 e.g. 'user'  | 'celeb'  | 'preset'  | 'mystery'  | 'concept' | 'mission'
                        'thumbnail_file_path': str,   # 썸네일 파일 S3 경로
                        'first_message': str,   # 캐릭터 인사말
                        'persona': str,
                        'llm_type': str,
                        'avatar_file_path': str,   # 아바타 glb 파일 S3 경로
                        'avatar_thumbnail_file_path': str,   # 아바타 썸네일 파일 S3 경로
                        'avatar_gender': str,   # 'F' | 'M'
                        "avatar_idle_motion_file_path": str   # 아바타 IDLE 모션 파일 S3 경로
                    },
                    ...
                ]
            },
            'chatroom_activated': {
                'id': int,
                'created_at': Decimal,
                'start_at': Decimal
            }
        }
    """
    try:
        content_id = int(content_id)
    except ValueError:
        return {}

    query = f"""
    SELECT
        C.id,
        CONCAT('/', TH.file_path) AS thumbnail_file_path,
        TH.id AS thumbnail_id,
        C.created_at,
        C.title,
        C.description,
        C.type,
        C.rating,
        COALESCE(UCC.user_chat_count, 0) AS user_chat_count,
        RT.id AS target_id,
        IF(CL.user_id IS NOT NULL, 1, 0) AS is_liked,
        CHATROOM.id AS chatroom_id,
        COUNT(DISTINCT L.email) AS like_count,
        COUNT(DISTINCT CC.user_id) AS user_count,
        GROUP_CONCAT(DISTINCT T.tag ORDER BY T.created_at SEPARATOR ',') AS tags,
        U.nickname AS creator_nickname,
        U.email AS creator_email
    FROM
        `content` AS C
    JOIN
        `user` AS U
        ON U.id = C.creator_id
    JOIN
        `thumbnail` AS TH
        ON TH.id = C.thumbnail_id
    JOIN
        `reaction_target` AS RT
        ON RT.content_id = C.id
    JOIN (
        SELECT
            C.id AS content_id,
            SUM(CCA.user_chat_count) AS user_chat_count
        FROM `content` AS C
        JOIN `content_connect` AS CC on C.id = CC.content_id
        LEFT JOIN `content_chatroom_active` AS CCA on CCA.connect_id = CC.id
        GROUP BY C.id
    ) AS UCC ON UCC.content_id = C.id
    LEFT JOIN (
        SELECT UL.target_id, US.id AS user_id
        FROM `like` AS UL
        JOIN `user` AS US ON US.email = UL.email
    ) AS CL ON CL.target_id = RT.id AND CL.user_id = {json.dumps(user_id)}
    JOIN
        `content_connect` AS CONNECT
        ON CONNECT.content_id = C.id
        AND CONNECT.active = 1
        AND CONNECT.chatroom_id IS NOT NULL
    JOIN
        `content_chatroom` AS CHATROOM
        ON CONNECT.chatroom_id = CHATROOM.id
    LEFT JOIN
        `content_chatroom_active` AS CC
        ON CC.connect_id = CONNECT.id
    LEFT JOIN
        `like` AS L
        ON L.target_id = RT.id
    LEFT JOIN
        `tag` AS T
        ON T.target_id = RT.id
    WHERE
        C.id = {content_id}
        AND C.active = 1
    GROUP BY C.id
    """
    cursor.execute(query)
    content_item = cursor.fetchone()

    if content_item:
        chatroom_id = content_item["chatroom_id"]
        content_item["created_at"] = time.totimestamp(content_item["created_at"])
        content_item["is_liked"] = True if content_item["is_liked"] else False
        content_item["tags"] = content_item["tags"].split(",") if content_item["tags"] else []
        content_item["user_chat_count"] = int(content_item["user_chat_count"])
        content_item["emojis"] = reaction_module.list_emoji_registered(
            content_item["target_id"],
            email,
            cursor=cursor
        )
        content_item["chatroom"] = chatroom_module.get_chatroom_details(chatroom_id, cursor=cursor)
        del content_item["target_id"], content_item["chatroom_id"]

        # 활성화 확인
        if user_id:
            content_item["chatroom_activated"] = chatroom_module.get_chatroom_activated(user_id, content_id=content_id, cursor=cursor)
        else:
            content_item["chatroom_activated"] = None

    else:
        content_item = {}

    return content_item


@preprocessing_cursor
def get_thumbnail(thumbnail_id: str, cursor: object = None) -> dict:
    """썸네일 조회"""
    query = f"SELECT * FROM `thumbnail` WHERE id = '{thumbnail_id}'"
    cursor.execute(query)
    return cursor.fetchone()


@preprocessing_cursor
def list_background_file_path(user_id: int = None, cursor: object = None) -> list:
    """배경화면 파일 경로 리스트

    :param user_id: 사용자 ID
        값이 있을 경우: 기본 배경화면 포함 사용자가 등록한 배경화면 조회
        값이 없을 경우: 기본 배경화면만 조회
    :param cursor: pymysql.connect().cursor()

    :return
        [
            'id': int,
            'name': str,
            'file_path': str,
            'user_id': int,
            'created_at': Decimal,
            'basic': bool   # 기본값 여부
        ]
    """
    query_where = ""
    if user_id:
        query_where = f"OR user_id = {user_id}"
    query = f"""
    SELECT
        id,
        name,
        file_path,
        user_id,
        created_at,
        basic
    FROM
        `background`
    WHERE
        basic = 1
        {query_where}
    ORDER BY basic DESC, created_at
    """
    cursor.execute(query)
    data = cursor.fetchall()
    for d in data:
        d["created_at"] = time.totimestamp(d["created_at"])
        d["basic"] = bool(d["basic"])
    return data


@preprocessing_cursor
def list_bgm_file_path(user_id: int = None, cursor: object = None) -> list:
    """배경음악 파일 경로 리스트

    :param user_id: 사용자 ID
        값이 있을 경우: 기본 배경음악 포함 사용자가 등록한 배경화면 조회
        값이 없을 경우: 기본 배경음악만 조회
    :param cursor: pymysql.connect().cursor()

    :return
        [
            'id': int,
            'name': str,
            'file_path': str,
            'user_id': int,
            'created_at': Decimal,
            'basic': bool   # 기본값 여부
        ]
    """
    query_where = ""
    if user_id:
        query_where = f"OR user_id = {user_id}"
    query = f"""
    SELECT
        id,
        name,
        file_path,
        user_id,
        created_at,
        basic
    FROM
        `bgm`
    WHERE
        basic = 1
        {query_where}
    ORDER BY basic DESC, created_at
    """
    cursor.execute(query)
    data = cursor.fetchall()
    for d in data:
        d["created_at"] = time.totimestamp(d["created_at"])
        d["basic"] = bool(d["basic"])
    return data


@preprocessing_cursor
def list_category(cursor: object = None) -> list:
    """컨텐츠 카테고리 순서 조회

    :return
        [
            {
                'category': str,
                'order': int
            },
            ...
        ]
    """
    query = """
    SELECT
        MS.category,
        MS.order
    FROM `main_sections` AS MS
    ORDER BY MS.order
    """
    cursor.execute(query)
    return cursor.fetchall()


@preprocessing_cursor
def list_content_chatroom(
    rating: str,
    order_type: int,
    user_id: int = None,
    search: str = None,
    category: str = None,
    own: bool = False,
    activated: bool = False,
    liked: bool = False,
    main: bool = False,
    page_size: int = 10,
    offset: int = 0,
    cursor: object = None
) -> list:
    """채팅 컨텐츠 리스트 조회

    :param rating: 조회할 컨텐츠 등급
        'G': 모든 연령 등급
        '18+': 성인 등급
    :param order_type: 정렬 순서
        1: 컨텐츠 생성 시간 내림차순
        2: 좋아요 수 내림차순
        3: 사용자 수 내림차순
        4: 사용자 최신 이용 내림차순
    :param user_id: 사용자 최신 이용 내림차순을 위해 적용할 사용자의 ID
    :param search: 타이틀, 설명, 태그 검색어
    :param category: 컨텐츠 카테고리
    :param own: user_id가 생성한 컨텐츠만 조회 여부
    :param activated: 사용자가 사용 중인 컨텐츠만 조회 여부
    :param liked: 사용자가 좋아요 한 컨텐츠만 조회 여부
    :param main: 메인 컨텐츠만 조회 여부
    :param page_size: page size for pagination
    :param offset: offset for pagination
    :param cursor: pymysql.connect().cursor()

    :return
        [
            {
                'content_id': int,   # 컨텐츠 ID
                'thumbnail_file_path': str,   # S3 저장된 썸네일 파일 경로
                'created_at': Decimal,   # 컨텐츠 생성된 시간
                'title': str,   # 제목
                'description': str,   # 설명
                'type': str,   # 컨텐츠 타입 (e.g. 'chatroom')
                'rating': str,   # 연령 등급 ('G': 모든 연령, '18+': 성인 등급)
                'latest_at': str,   # 가장 최근 사용한 시간
                'like_count': int,   # 좋아요 수
                'user_count': int,   # 사용자 수
                'user_chat_count': int,   # 사용자 채팅 수
                'tags': list,   # 태그 (e.g. ['aaa', 'bbb', 'ccc'])
                'nickname': str,   # 생성자 닉네임,
                'is_liked': bool   # 사용자가 좋아요 했는지 확인
            },
            ...
        ]
    """
    conditions = [
        "C.active = 1",
        f"C.type = '{const.CONTENT_TYPE_CHATROOM}'",
        "B.target_id IS NULL"
    ]
    order_by = "C.modified_at DESC"
    query_having = ""

    # 컨텐츠 등급 적용 (모든 연령 등급일 경우 성인 컨텐츠 제외)
    if rating == const.CONTENT_RATING_GENERAL:
        conditions.append(f"C.rating = '{rating}'")

    # 카테고리 적용
    if category:
        conditions.append(f"C.category = '{category}'")

    # user_id 컨텐츠 조회
    if own and user_id:
        conditions.append(f"C.creator_id = {user_id}")

    # 사용자 사용 중인 컨텐츠만 조회
    if activated:
        conditions.append("CCA.latest_at IS NOT NULL")
        conditions.remove("C.active = 1")

    # 사용자가 좋아요 한 컨텐츠만 조회
    if liked:
        conditions.append("CL.user_id IS NOT NULL")

    # 검색어 적용
    if search:
        having_conditions = []
        having_conditions.append(f"UPPER(C.title) LIKE UPPER('%{search}%')")
        having_conditions.append(f"UPPER(C.description) LIKE UPPER('%{search}%')")
        having_conditions.append(f"UPPER(tags) LIKE UPPER('%{search}%')")
        query_having = "HAVING " + " OR ".join(having_conditions)

    # 메인 컨텐츠 적용
    if main:
        conditions.append("C.id in (SELECT content_id FROM `content_main`)")

    # 정렬 순서
    if order_type == 1:
        pass
    elif order_type == 2:
        order_by = "like_count DESC, " + order_by
    elif order_type == 3:
        order_by = "user_count DESC, " + order_by
    elif order_type == 4 and user_id:
        order_by = "latest_at DESC, " + order_by

    query = f"""
    SELECT
        C.id AS content_id,
        CONCAT('/', TH.file_path) AS thumbnail_file_path,
        C.created_at,
        C.title,
        C.description,
        C.type,
        C.rating,
        COALESCE(UCC.user_chat_count, 0) AS user_chat_count,
        IF(COUNT(CL.user_id) > 0, 1, 0) AS is_liked,
        MAX(CC.latest_at) AS latest_at,
        COUNT(DISTINCT L.email) AS like_count,
        COUNT(DISTINCT CC.user_id) AS user_count,
        GROUP_CONCAT(DISTINCT T.tag ORDER BY T.created_at SEPARATOR ',') AS tags,
        U.nickname,
        C.active
    FROM
        `content` AS C
    JOIN
        `user` AS U
        ON U.id = C.creator_id
    JOIN
        `reaction_target` AS RT
        ON RT.content_id = C.id
    JOIN
        `content_connect` AS CONNECT
        ON CONNECT.content_id = C.id
        AND CONNECT.active = 1
        AND CONNECT.chatroom_id IS NOT NULL
    JOIN
        `thumbnail` AS TH
        ON TH.id = C.thumbnail_id
    JOIN (
        SELECT
            C.id AS content_id,
            SUM(CCA.user_chat_count) AS user_chat_count
        FROM `content` AS C
        JOIN `content_connect` AS CC on C.id = CC.content_id
        LEFT JOIN `content_chatroom_active` AS CCA on CCA.connect_id = CC.id
        GROUP BY C.id
    ) AS UCC ON UCC.content_id = C.id
    LEFT JOIN
        `content_chatroom_active` AS CC
        ON CC.connect_id = CONNECT.id
    LEFT JOIN
        `content_chatroom_active` AS CCA
        ON CCA.connect_id = CONNECT.id
        AND CCA.user_id = {json.dumps(user_id)}
        AND CCA.active = 1
    LEFT JOIN (
        SELECT UL.target_id, US.id AS user_id
        FROM `like` AS UL
        JOIN `user` AS US ON US.email = UL.email
    ) AS CL ON CL.target_id = RT.id AND CL.user_id = {json.dumps(user_id)}
    LEFT JOIN
        `like` AS L
        ON L.target_id = RT.id
    LEFT JOIN
        `block` AS B
        ON B.target_id = RT.id
    LEFT JOIN
        `tag` AS T
        ON T.target_id = RT.id
    WHERE
        {' AND '.join(conditions)}
    GROUP BY C.id
    {query_having}
    ORDER BY {order_by}
    LIMIT {page_size} OFFSET {offset}
    """
    cursor.execute(query)
    data = cursor.fetchall()
    ret = []
    for d in data:
        if d.get("tags"):
            d["tags"] = d["tags"].split(",")
        d["is_liked"] = True if d["is_liked"] else False
        d["created_at"] = time.totimestamp(d["created_at"])
        d["user_chat_count"] = int(d["user_chat_count"])
        if not d["active"]:
            ret.append({})
        else:
            del d["active"]
            ret.append(d)
    return ret


def list_search(user_id: int) -> list:
    """컨텐츠 검색어 이력 최신 순으로 조회

    :param user_id: 사용자 ID

    :return
        [
            {
                'timestamp': Decimal,
                'keyword': str
            },
            ...
        ]
    """
    table_name = "idolmaster_content_search"
    history_tb = dynamodb.get_resource_obj(table_name)
    data = dynamodb.query_all_items(
        history_tb,
        Key("user_id").eq(user_id),
        index_forward=False
    )
    ch_key = []
    ret = []
    for d in data:
        keyword = d["keyword"]
        if keyword not in ch_key:
            ret.append({
                "timestamp_at": d["timestamp_at"],
                "keyword": keyword
            })
            ch_key.append(keyword)
    return ret


@preprocessing_cursor
def list_tag(cursor: object = None) -> list:
    """태그 가장 많이 사용된 순서(내림차순)로 리스트 조회

    :return
        [
            {
                'tag': str,
                'created_at': Decimal,
                'count': int
            }
        ]
    """
    query = """
    SELECT
        T.tag,
        T.created_at,
        RT.content_id,
        COUNT(T.target_id) AS count
    FROM `tag` AS T
    JOIN
        `reaction_target` AS RT
        ON RT.id = T.target_id AND content_id IS NOT NULL
    JOIN
        `content` AS C
        ON RT.content_id = C.id AND C.active = 1
    GROUP BY T.tag
    ORDER BY count DESC
    """
    cursor.execute(query)
    data = cursor.fetchall()
    for d in data:
        d["created_at"] = time.totimestamp(d["created_at"])
    return data


def put_file_to_s3(pre_file_path: str, file_object: object, extension: str) -> str:
    """S3에 파일 저장.

    :param pre_file_path: 저장될 S3 폴더 경로
    :param file_object: 이미지 파일 (Bytes)
    :param extension: 이미지 파일 확장자

    :return: 저장된 S3 파일 경로
    """
    uuid = shortuuid.ShortUUID().random(length=20)
    extension_str = f".{extension}" if extension else ""
    file_path = f"{pre_file_path}/{uuid}{extension_str}"
    bucket_name = const.S3_BUCKET_NAME[os.environ["AWS_REGION"]][
        os.environ["API_ALIAS"]
    ]
    client.s3_client.put_object(Bucket=bucket_name, Key=file_path, Body=file_object)
    print(f"S3 put_object {bucket_name} {file_path}")
    return file_path


@preprocessing_cursor
def save_background_file_path(file_path: str, name: str, user_id: int, basic: bool, cursor: object = None) -> int:
    """배경화면 파일 경로를 db에 저장

    :param file_path: 저장된 파일 경로
    :param name: db 저장될 배경화면 이름
    :param user_id: 저장한 사용자 ID
    :param basic: 기본 배경화면 여부
    :param cursor: pymysql.connect().cursor()

    :return: 생성된 배경화면 ID
    """
    query = """
    INSERT INTO `background` (file_path, name, user_id, basic)
    VALUES (%s, %s, %s, %s)
    RETURNING id
    """
    cursor.execute(query, (file_path, name, user_id, basic))
    return cursor.fetchone()["id"]


@preprocessing_cursor
def save_bgm_file_path(file_path: str, name: str, user_id: int, basic: bool, tags: list = None, cursor: object = None) -> int:
    """배경음악 파일 경로를 db에 저장

    :param file_path: 저장된 파일 경로
    :param name: db 저장될 배경음악 이름
    :param user_id: 저장한 사용자 ID
    :param basic: 기본 배경음악 여부
    :param tags: 저장된 태그 리스트 (e.g. ['aaa','bbb', ...])
    :param cursor: pymysql.connect().cursor()

    :return: 생성된 배경음악 ID
    """
    query = """
    INSERT INTO `bgm` (file_path, name, user_id, basic)
    VALUES (%s, %s, %s, %s)
    RETURNING id
    """
    cursor.execute(query, (file_path, name, user_id, basic))
    bgm_id = cursor.fetchone()["id"]
    if tags:
        target_id = reaction_module.get_reaction_id(bgm_id=bgm_id, cursor=cursor)
        reaction_module.create_tag(target_id, tags, cursor=cursor)
    return bgm_id


def save_search_history(user_id: int, search: str) -> None:
    """컨텐츠 검색어 이력 저장

    :param user_id: 검색한 사용자 ID
    :param search: 검색어
    """
    table_name = "idolmaster_content_search"
    dynamodb.put_item(table_name, {
        "user_id": user_id,
        "timestamp_at": time.timestampnow(),
        "keyword": search
    })


@preprocessing_cursor
def save_thumbnail_file_path(file_path: str, user_id: int, basic: bool, cursor: object = None) -> int:
    """썸네일 파일 경로를 db에 저장

    :param file_path: 저장된 파일 경로
    :param user_id: 저장한 사용자 ID
    :param basic: 기본 썸네일 여부
    :param cursor: pymysql.connect().cursor()

    :return: 생성된 썸네일 ID
    """
    query = """
    INSERT INTO `thumbnail` (file_path, user_id, basic)
    VALUES (%s, %s, %s)
    RETURNING id
    """
    cursor.execute(query, (file_path, user_id, basic))
    return cursor.fetchone()["id"]


@preprocessing_cursor
def update_content(
    content_id: int,
    title: str,
    description: str,
    thumbnail_id: int,
    rating: str,
    cursor: object = None
) -> None:
    """컨텐츠 수정

    :param content_id: 컨텐츠 ID
    :param title: 제목
    :param description: 설목
    :param thumbnail_id: 썸네일 ID
    :param rating: 컨텐츠 등급
    :param cursor: pymysql.connect().cursor()
    """
    query = f"""
    UPDATE `content`
    SET
        title = '{title}',
        description = '{description}',
        thumbnail_id = {thumbnail_id},
        rating = '{rating}'
    WHERE
        id = {content_id}
    """
    cursor.execute(query)
