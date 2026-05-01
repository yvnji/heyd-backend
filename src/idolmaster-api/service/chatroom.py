import datetime
import os
from decimal import Decimal

from boto3.dynamodb.conditions import Key

import const
from lib import time
from lib.decorator import preprocessing_cursor
from service import avatar as avatar_module
from service import character as character_module
from service import share as share_module
from service import user as user_module
from thirdparty import dynamodb
from thirdparty import llm_api


@preprocessing_cursor
def create_chatroom(
    title: str,
    character_ids: list,
    creator_id: int,
    background_name: str,
    background_id: str,
    bgm_id: int = None,
    cursor: object = None
) -> int:
    """컨텐츠에서 사용할 채팅방 생성

    :param title: title
    :param character_ids: 채팅방 캐릭터 ID 리스트
    :param creator_id: 생성자 ID
    :param background_name: 배경화면 이름
    :param background_id: 배경화면 iD
    :param bgm_id: bgm ID
    :param cursor: pymysql.connect().cursor()

    :return: 생성된 채팅방 ID
    """
    query = """
    INSERT INTO `content_chatroom` (title, background_name, background_id, bgm_id, creator_id)
    VALUES (%s, %s, %s, %s, %s)
    RETURNING id
    """
    cursor.execute(query, (title, background_name, background_id, bgm_id, creator_id))
    chatroom_id = cursor.fetchone()["id"]

    # 캐릭터 등록
    query_values = []
    query_params = []
    timestamp_at = time.timestampnow()
    for cid in character_ids:
        query_values.append("(%s, %s, %s)")
        query_params.extend([chatroom_id, cid, time.fromtimestamp(timestamp_at)])
        timestamp_at += 1
    query_values = ", ".join(query_values)
    query = f"""
    INSERT INTO `content_chatroom_character` (chatroom_id, character_id, created_at)
    VALUES {query_values}
    """
    cursor.execute(query, query_params)

    return chatroom_id


@preprocessing_cursor
def get_chatroom(chatroom_id: int, cursor: object = None) -> dict:
    """컨텐츠에서 사용할 채팅방 기본 조회

    :param chatroom_id: 채팅방 ID (Table : content_chatroom)
    :param cursor: pymysql.connect().cursor()

    :return
        {
            'id': int,
            'title': str,
            'background_file_path': str,
            'bgm_file_path': str,
            'creator_id': int
        }
    """
    query = f"""
    SELECT
        CC.id,
        CC.title,
        BGI.file_path AS background_file_path,
        BGM.file_path AS bgm_file_path,
        CC.creator_id
    FROM `content_chatroom` AS CC
    JOIN `background` AS BGI ON CC.background_id = BGI.id
    LEFT JOIN `bgm` AS BGM ON CC.bgm_id = BGM.id
    WHERE CC.id = {chatroom_id}
    """
    cursor.execute(query)
    data = cursor.fetchone()
    return data if data else {}


@preprocessing_cursor
def get_chatroom_by_content(content_id: int, cursor: object = None) -> dict:
    """컨텐츠에서 사용할 채팅방 기본 조회

    :param content_id: 컨텐츠 ID
    :param cursor: pymysql.connect().cursor()

    :return
        {
            'id': int,
            'title': str,
            'background_file_path': str,
            'bgm_file_path': str,
            'creator_id': int,
            'connect_id': int
        }
    """
    query = f"""
    SELECT
        CC.id,
        CC.title,
        BGM.file_path AS background_file_path,
        BGI.file_path AS bgm_file_path,
        CC.creator_id,
        C.id AS connect_id
    FROM `content_connect` AS C
    JOIN `content_chatroom` AS CC ON C.chatroom_id = CC.id
    JOIN `background` AS BGI ON CC.background_id = BGI.id
    LEFT JOIN `bgm` AS BGM ON CC.bgm_id = BGM.id
    WHERE
        C.content_id = {content_id}
        AND C.active = 1
        AND C.chatroom_id IS NOT NULL
    """
    cursor.execute(query)
    data = cursor.fetchone()
    return data if data else {}


@preprocessing_cursor
def get_chatroom_activated(user_id: int, content_id: int = None, chatroom_id: int = None, cursor: object = None) -> dict:
    """컨텐츠에서 현재 활성화된 채팅방 정보 조회
    content_id 또는 chatroom_id 중 하나로 조회

    :param user_id: 사용자 ID
    :param content_id: 컨텐츠 ID
    :param chatroom_id: 컨텐츠에 등록되어 있는 채팅방 ID (Table : content_chatroom)
    :param cursor: pymysql.connect().cursor()

    :return
        {
            'id': int,   # content_chatroom_active ID
            'start_at': Decimal,
            'latest_at': Decimal
        }
    """
    data = {}
    query_where = ""
    if content_id:
        query_where = f"AND content_id = {content_id}"
    elif chatroom_id:
        query_where = f"AND chatroom_id = {chatroom_id}"
    query_connect = f"""
    SELECT id
    FROM `content_connect`
    WHERE
        active = 1
        {query_where}
    """
    cursor.execute(query_connect)
    content_connect = cursor.fetchone()
    if content_connect:
        connect_id = content_connect["id"]
        query_chatroom_activated = f"""
        SELECT
            id,
            start_at,
            latest_at
        FROM `content_chatroom_active`
        WHERE
            active = 1
            AND connect_id = {connect_id}
            AND user_id = {user_id}
        """
        cursor.execute(query_chatroom_activated)
        data = cursor.fetchone()
        if data:
            data["start_at"] = time.totimestamp(data["start_at"])
            data["latest_at"] = time.totimestamp(data["latest_at"])
        else:
            data = {}
    return data


@preprocessing_cursor
def get_chatroom_activated_by_id(chatroom_activated_id: int, cursor: object = None) -> dict:
    """활성화된 채팅방 정보 조회

    :param chatroom_activated_id: 활성화된 채팅방 ID
    :param cursor: pymysql.connect().cursor()

    :return
        {
            'content_id': int,
            'chatroom_id': int,
            'user_id': int,
            'start_at': datetime,
            'latest_at': datetime
        }
    """
    query = f"""
    SELECT
        CCA.user_id,
        CCA.start_at,
        CCA.latest_at,
        CC.content_id,
        CC.chatroom_id
    FROM `content_chatroom_active` AS CCA
    JOIN `content_connect` AS CC ON CCA.connect_id = CC.id
    WHERE CCA.id = {chatroom_activated_id}
    """
    cursor.execute(query)
    data = cursor.fetchone()
    return data if data else {}


@preprocessing_cursor
def get_chatroom_details(chatroom_id: int, cursor: object = None) -> dict:
    """컨텐츠에서 사용하는 채팅방 정보 조회

    :param chatroom_id: 채팅방 ID (table content_chatroom)
    :param cursor: pymysql.connect().cursor()

    :return
        {
            'id': int,
            'title': str,
            'background_name': str,
            'creator_nickname': str,
            'creator_email': str,
            'background_file_path': str,
            'background_id': int,
            'bgm_file_path': str,
            'bgm_name': str,
            'bgm_id': int,
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
        }
    """
    query_chatroom = f"""
    SELECT
        C.id,
        C.title,
        C.background_name,
        U.nickname AS creator_nickname,
        U.email AS creator_email,
        CONCAT('/', BGI.file_path) AS background_file_path,
        BGI.id AS background_id,
        CONCAT('/', BGM.file_path) AS bgm_file_path,
        BGM.name AS bgm_name,
        BGM.id AS bgm_id,
        GROUP_CONCAT(CC.character_id ORDER BY CC.created_at SEPARATOR ',') AS character_ids
    FROM `content_chatroom` AS C
    JOIN `user` AS U ON U.id = C.creator_id
    JOIN `background` AS BGI ON C.background_id = BGI.id
    LEFT JOIN `bgm` AS BGM ON C.bgm_id = BGM.id
    LEFT JOIN `content_chatroom_character` AS CC ON CC.chatroom_id = C.id
    WHERE
        C.id = {chatroom_id}
        AND C.active = 1
    GROUP BY C.id
    """
    cursor.execute(query_chatroom)
    chatroom_item = cursor.fetchone()
    if chatroom_item:
        chatroom_item["characters"] = []
        for character_id in chatroom_item["character_ids"].split(","):
            chatroom_item["characters"].append(character_module.get_character_details_v2(character_id, cursor=cursor))
        del chatroom_item["character_ids"]
    else:
        chatroom_item = {}
    return chatroom_item


@preprocessing_cursor
def list_chat(
    chatroom_activated_id: int,
    start_at: Decimal,
    last_evaluated_key: dict = None,
    user_id: int = None,
    character_id: str = None,
    limit: int = 150,
    cursor: object = None
) -> list:
    """활성화된 채팅방 채팅 이력 조회

    :param chatroom_activated_id: 활성화된 채팅방 ID
    :param start_at: 채팅 이력 시작 시간 timestamp
    :param last_evaluated_key: last_evaluated_key
    :param limit: 조회할 최대 채팅 수
    :param cursor: pymysql.connect().cursor()

    :return
        {
            'chats': [
                {
                    'chatroom_id': int,
                    'chat': str,
                    'timestamp_at': Decimal,
                    'chatroom_activated_id': int,
                    'character_id': str,   # 채팅 보낸 캐릭터
                                           # OR user_id가 있을 경우 채팅 대상 캐릭터
                    'user_id': int   # 사용자가 보낸 채팅일 경우만 존재
                    'user_nickname': str   # 사용자가 보낸 채팅일 경우만 존재
                },
                ...
            ],
            'last_evaluated_key': {
                'chatroom_id': int,
                'timestamp_at': Decimal
            }
        }
    """
    table_name = "idolmaster_content_chat"
    scan_condition = None
    nickname_dict = {}

    if user_id:
        scan_condition = Key("user_id").eq(user_id)
    elif character_id:
        scan_condition = Key("character_id").eq(character_id)

    previous_chat, last_evaluated_key = dynamodb.fetch_data_query(
        table_name,
        Key("chatroom_activated_id").eq(chatroom_activated_id) & Key("timestamp_at").gte(start_at),
        scan_condition=scan_condition,
        index_name="chatroom_activated_id-timestamp_at-index",
        limit=limit,
        index_forward=False,  # 내림차순
        last_evaluated_key=last_evaluated_key,
    )

    # 오름차순으로 정렬
    previous_chat.sort(key=lambda x: x["timestamp_at"])

    # nickname 조회
    for chat in previous_chat:
        # user nickname 조회
        user_id = chat.get("user_id")
        if user_id:
            if user_id not in nickname_dict:
                nickname_dict[user_id] = user_module.get_user_info_by_id(user_id, cursor=cursor)["nickname"]
            chat["user_nickname"] = nickname_dict[user_id]

        # character nickname 조회
        character_id = chat["character_id"]
        if character_id not in nickname_dict:
            nickname_dict[character_id] = character_module.get_character(character_id, cursor=cursor)["name"]
        chat["character_name"] = nickname_dict[character_id]

    return {"chats": previous_chat, "last_evaluated_key": last_evaluated_key}


@preprocessing_cursor
def reset_chatroom_activated(chatroom_id: int, chatroom_activated_id: int, cursor: object = None) -> None:
    """활성화된 채팅방 초기화

    :param chatroom_id: chatroom ID
    :param chatroom_activated_id: 활성화된 채팅방 ID
    :param cursor: pymysql.connect().cursor()
    """
    query = f"""
    UPDATE `content_chatroom_active`
    SET start_at = CURRENT_TIMESTAMP()
    WHERE id = {chatroom_activated_id}
    """
    cursor.execute(query)

    send_first_chat(chatroom_id, chatroom_activated_id, time.timestampnow(), cursor=cursor)


@preprocessing_cursor
def prepare_llm_chat_input(
    character_ids: list,
    chat_type: str,
    start_at: Decimal = None,
    user_id: int = None,
    other_user_ids: list = [],
    chatroom_activated_id: int = None,
    shared_chatroom_id: str = None,
    cursor: object = None
) -> dict:
    """LLM 포맷에 맞게 데이터셋 변환

    :param character_ids: 캐릭터 ID 리스트 (첫번째 순서의 캐릭터가 채팅 대상)
    :param chat_type: 채팅 타입 (현재 content, share 만 구현 됨)
    :param start_at: 채팅 이력 시작 시간 (chat_type이 content일 경우 필수)
    :param user_id: 사용자 ID (chat_type이 share 아닐 경우 필수)
    :param other_user_ids: 사용자 외 유저 ID 리스트 (chat_type이 groupchat일 경우 존재)
    :param chatroom_activated_id: 활성화된 채팅방 ID (chat_type이 content일 경우 필수)
    :param shared_chatroom_id: 공유 채팅방 ID (chat_type이 share일 경우 필수)
    :param cursor: pymysql.connect().cursor()

    :return
        {
            "character_profiles": [     // 캐릭터 프로필 리스트 (첫번째 캐릭터가 채팅 대상)
                {
                    "character_id": str,
                    "name": str,
                    "type": str,
                    "basic_info": str,
                    "main_prompt": str,
                    "options": str,
                    "avatar_file_path": str,
                    "gender": str
                },
                ...
            ],
            "deleted_profiles": [    // 삭제된 프로필 리스트 (삭제된 캐릭터 또는 삭제된 유저)
                {
                    "id": str    // 캐릭터 ID 또는 유저 ID
                },
                ...
            ],
            "user_profiles": [
                {
                    "nickname": str,
                    "birth_date": date,
                    "gender": str
                },
                ...
            ],
            "name_dict": {
                "{character_id or email or user_id}": str    // 캐릭터 이름 또는 유저 닉네임
            },
            "chat_histories": [
                {
                    "id": str,
                    "msg": str
                },
                ...
            ]
        }
    """
    name_dict = {}    # 캐릭터 이름 또는 유저 닉네임
    character_profiles = []    # 캐릭터 프로필 리스트 (첫번째 캐릭터가 채팅 대상)
    deleted_profiles = []    # 삭제된 프로필 리스트 (삭제된 캐릭터 또는 삭제된 유저)
    user_profiles = []    # 사용자 프로필 리스트
    chat_histories = []    # 채팅 이력 리스트

    # character llm option 조회
    query_option = """
    SELECT
        main_prompt,
        options
    FROM `character_llm`
    """
    cursor.execute(query_option)
    character_llm = cursor.fetchone()

    # 캐릭터 정보 조회
    character_ids_str = ", ".join([f"'{id}'" for id in character_ids])
    query = f"""
    SELECT
        C.character_id,
        C.name,
        C.type,
        C.active,
        CP.basic_info,
        A.avatar_file_path,
        A.gender
    FROM `character` AS C
    JOIN `avatar` AS A ON C.avatar_id = A.avatar_id
    JOIN `character_persona` as CP ON C.character_id = CP.character_id
    WHERE C.character_id IN ({character_ids_str})
    """
    cursor.execute(query)
    character_profiles = cursor.fetchall()
    for c in character_profiles:
        c["main_prompt"] = character_llm["main_prompt"]
        c["options"] = character_llm["options"]
        name_dict[c["character_id"]] = c["name"]

        # 삭제된 캐릭터 조회
        if not c["active"]:
            deleted_profiles.append({
                "id": c["character_id"]
            })

        del c["active"]

    # 파라미터 character_ids 순서에 맞게 정렬
    order_dict = {val: idx for idx, val in enumerate(character_ids)}
    character_profiles = sorted(character_profiles, key=lambda x: order_dict[x["character_id"]])

    if chat_type == const.CHAT_TYPE_SHARE:
        # 게스트 정보
        shared_chatroom_item = share_module.get_shared_chatroom(shared_chatroom_id, cursor=cursor)
        user_profiles.append({
            "nickname": shared_chatroom_item["nickname"],
            "birth_date": shared_chatroom_item["birth_date"],
            "gender": shared_chatroom_item["gender"]
        })
        name_dict[shared_chatroom_item["nickname"]] = shared_chatroom_item["nickname"]

        # 채팅 이력 조회
        chats = share_module.list_shared_chatroom_chats(
            shared_chatroom_id,
            character_ids,
            shared_chatroom_item["chatroom_activated_id"],
            shared_chatroom_item["created_at"],
            shared_chatroom_item["start_at"],
            cursor=cursor
        )
        other_user_nicknames = []
        for c in chats:
            item = {}
            if c.get("user_nickname"):
                item["id"] = c["user_nickname"]
                if c["user_nickname"] not in other_user_nicknames:
                    other_user_nicknames.append(c["user_nickname"])
                    user_profiles.append({
                        "nickname": c["user_nickname"],

                        # 임의 지정
                        "birth_date": datetime.date(year=2000, month=1, day=1),
                        "gender": "Male"

                    })
                    name_dict[c["user_nickname"]] = c["user_nickname"]
            elif c.get("guest_nickname"):
                item["id"] = c["guest_nickname"]
                if c["guest_nickname"] not in name_dict:
                    name_dict[c["guest_nickname"]] = c["guest_nickname"]
            else:
                item["id"] = c["character_id"]
            item["msg"] = c["chat"]
            chat_histories.append(item)

    else:
        # 사용자 정보
        user_item = user_module.get_user_info_by_id(user_id, cursor=cursor)
        user_profiles.append({
            "nickname": user_item["nickname"],
            "birth_date": user_item["birth_date"],
            "gender": user_item["gender"]
        })

        if chat_type == const.CHAT_TYPE_CONTENT:
            name_dict[str(user_item["id"])] = user_item["nickname"]

            # 채팅 이력 조회
            chats = list_chat(chatroom_activated_id, start_at)["chats"][::-1]   # 내림차순
            for c in chats:
                item = {}
                if c.get("user_id"):
                    item["id"] = str(c["user_id"])
                else:
                    item["id"] = c["character_id"]
                item["msg"] = c["chat"]
                chat_histories.append(item)

        # TODO: 추후 구현
        # elif chat_type == const.CHAT_TYPE_CHARACTER:
        #     pass
        # elif chat_type == const.CHAT_TYPE_GROUP:
        #     pass
        # elif chat_type == const.CHAT_TYPE_GAME:
        #     pass

        else:
            raise Exception

    return {
        "character_profiles": character_profiles,
        "deleted_profiles": deleted_profiles,
        "user_profiles": user_profiles,
        "name_dict": name_dict,
        "chat_histories": chat_histories
    }


@preprocessing_cursor
def send_chat(
    character_ids: list,
    chat_type: str,
    chat: str,
    start_at: Decimal = None,
    user_id: int = None,
    other_user_ids: list = [],
    chatroom_activated_id: int = None,
    shared_chatroom_id: str = None,
    guest_id: str = None,
    block_reason: str = None,
    safe_chat: bool = True,
    cursor: object = None
) -> dict:
    """LLM 포맷에 맞게 데이터셋 변환

    :param character_ids: 캐릭터 ID 리스트 (첫번째 순서의 캐릭터가 채팅 대상)
    :param chat_type: 채팅 타입 (현재 content, share 만 구현 됨)
    :param chat: 채팅 내용
    :param start_at: 채팅 이력 시작 시간 (chat_type이 content일 경우 필수)
    :param user_id: 사용자 ID (chat_type이 share 아닐 경우 필수)
    :param other_user_ids: 사용자 외 유저 ID 리스트 (chat_type이 groupchat일 경우 존재)
    :param chatroom_activated_id: 활성화된 채팅방 ID (chat_type이 content일 경우 필수)
    :param shared_chatroom_id: 공유 채팅방 ID (chat_type이 share일 경우 필수)
    :param guest_id: 게스트 ID (chat_type이 share일 경우 필수)
    :param block_reason: 검열 이유
    :param safe_chat: 안전 채팅 여부
    :param cursor: pymysql.connect().cursor()

    :return: 채팅 보내기 결과
        {
            'character_id': str,
            'character_name': str,
            'timestamp_at': Decimal,
            'message': str,
            'motion_file_path': str,
            'block_reason': str
        }
    """
    print(f"chat_type: {chat_type}")
    chat_table_name = None
    answer = None
    analysis_emotion = None
    put_item_user = None
    put_item_character = None
    timestamp_now = time.timestampnow()
    query_list = []

    # LLM 포맷에 맞게 데이터셋 변환
    llm_input = prepare_llm_chat_input(
        character_ids,
        chat_type,
        start_at=start_at,
        user_id=user_id,
        other_user_ids=other_user_ids,
        chatroom_activated_id=chatroom_activated_id,
        shared_chatroom_id=shared_chatroom_id,
        cursor=cursor
    )
    print(llm_input)

    if chat_type == const.CHAT_TYPE_SHARE:
        chat_table_name = "idolmaster_content_chat_shared"

        # 사용자 채팅 데이터
        put_item_user = {
            "shared_chatroom_id": shared_chatroom_id,
            "timestamp_at": timestamp_now,
            "chat": chat,
            "character_id": character_ids[0],
            "guest_nickname": llm_input["user_profiles"][0]["nickname"],
            "guest_id": guest_id
        }

        # 그룹채팅으로 LLM 적용
        list_content = llm_api.content_merge_groupchat(
            llm_input["character_profiles"][0],
            llm_input["character_profiles"][1:],
            llm_input["user_profiles"],
            [{
                "id": put_item_user["guest_nickname"],
                "msg": put_item_user["chat"]
            }] + llm_input["chat_histories"],
            llm_input["deleted_profiles"],
            llm_input["name_dict"],
            os.environ["API_ALIAS"]
        )

        # OpenAI API 생성 & 답변 추출
        answer, analysis_emotion, block_reason = llm_api.call_llm_groupchat(
            "gpt-4o",
            list_content,
            block_reason,
            None,
            None,
            None,
            llm_input["character_profiles"][0]["options"],
            os.environ["API_ALIAS"],
            safe_chat
        )

        # 캐릭터 답변 데이터
        put_item_character = {
            "shared_chatroom_id": shared_chatroom_id,
            "timestamp_at": time.timestampnow(),
            "chat": answer,
            "character_id": character_ids[0]
        }

        # 사용 횟수 없데이트 쿼리
        query_list.append(("""
        UPDATE `content_chatroom_shared`
        SET usage_count = usage_count + 1
        WHERE id = %s
        """, (shared_chatroom_id)))
        query_list.append(("""
        UPDATE `content_chatroom_shared_guest`
        SET usage_count = usage_count + 1
        WHERE shared_chatroom_id = %s AND id = %s
        """, (shared_chatroom_id, guest_id)))

    elif chat_type == const.CHAT_TYPE_CONTENT:
        chatroom_activated_item = get_chatroom_activated_by_id(chatroom_activated_id, cursor=cursor)
        chat_table_name = "idolmaster_content_chat"

        # 사용자 채팅 데이터
        put_item_user = {
            "chatroom_id": chatroom_activated_item["chatroom_id"],
            "timestamp_at": timestamp_now,
            "chatroom_activated_id": chatroom_activated_id,
            "chat": chat,
            "character_id": character_ids[0],
            "user_id": user_id
        }

        print(f"character_ids: {character_ids}")
        print(f"character profiles: {llm_input['character_profiles']}")

        # 캐릭터 수에 따라 채팅 적용
        if len(character_ids) == 1:
            list_content = llm_api.content_merge_chat(
                llm_input["character_profiles"][0],
                llm_input["user_profiles"][0],
                [{
                    "id": str(put_item_user["user_id"]),
                    "msg": put_item_user["chat"]
                }] + llm_input["chat_histories"],
                os.environ["API_ALIAS"]
            )
            answer, analysis_emotion, block_reason = llm_api.call_llm_chat(
                "gpt-4o",
                list_content,
                block_reason,
                None,
                None,
                None,
                llm_input["character_profiles"][0]["options"],
                os.environ["API_ALIAS"],
                llm_input["character_profiles"][0]["type"],
                safe_chat
            )

        elif len(character_ids) > 1:
            list_content = llm_api.content_merge_groupchat(
                llm_input["character_profiles"][0],
                llm_input["character_profiles"][1:],
                llm_input["user_profiles"],
                [{
                    "id": str(put_item_user["user_id"]),
                    "msg": put_item_user["chat"]
                }] + llm_input["chat_histories"],
                llm_input["deleted_profiles"],
                llm_input["name_dict"],
                os.environ["API_ALIAS"]
            )
            answer, analysis_emotion, block_reason = llm_api.call_llm_groupchat(
                "gpt-4o",
                list_content,
                block_reason,
                None,
                None,
                None,
                llm_input["character_profiles"][0]["options"],
                os.environ["API_ALIAS"],
                safe_chat
            )

        else:
            raise Exception

        # 캐릭터 답변 데이터
        put_item_character = {
            "chatroom_id": chatroom_activated_item["chatroom_id"],
            "timestamp_at": time.timestampnow(),
            "chatroom_activated_id": chatroom_activated_id,
            "chat": answer,
            "character_id": character_ids[0],
        }

        # 최신 채팅시간 & 캐릭터 사용 횟수 & 사용자 채팅 수 없데이트 쿼리
        query_list.append(("""
        UPDATE `content_chatroom_active`
        SET latest_at = %s,
        user_chat_count = user_chat_count + 1
        WHERE id = %s
        """, (time.fromtimestamp(timestamp_now), chatroom_activated_id)))
        query_list.append(("""
        UPDATE `character`
        SET total_usage_count = total_usage_count + 1
        WHERE character_id = %s
        """, (character_ids[0])))

    else:
        raise Exception

    print(f"answer: {answer}")
    print(f"analysis_emotion: {analysis_emotion}")
    print(f"block_reason: {block_reason}")

    # 채팅 검열 성공
    if answer and not block_reason:
        block_reason = None

        # 사용자 채팅 저장
        dynamodb.put_item(chat_table_name, put_item_user)

        # 답변 저장
        dynamodb.put_item(chat_table_name, put_item_character)

        # DB 업데이트
        for query, param in query_list:
            cursor.execute(query, param)

    ret = {
        "character_id": character_ids[0],
        "character_name": llm_input["character_profiles"][0]["name"],
        "timestamp_at": timestamp_now,
        "message": answer,
        "block_reason": block_reason
    }

    # Emotion file path
    motion_path = avatar_module.get_emotion_retargeting(
        analysis_emotion, llm_input["character_profiles"][0]["avatar_file_path"], llm_input["character_profiles"][0]["gender"])
    ret["motion_file_path"] = "/" + motion_path

    return ret


@preprocessing_cursor
def send_first_chat(
    chatroom_id: int,
    chatroom_activated_id: int,
    timestamp_at: Decimal,
    cursor: object = None
) -> None:
    """캐릭터들의 첫 메세지 발송

    :param chatroom_id: chatroom ID
    :param chatroom_activated_id: 활성화된 채팅방 ID
    :param timestamp_at: timestamp
    :param cursor: pymysql.connect().cursor()
    """
    # 첫 메세지 발송
    table_name = "idolmaster_content_chat"
    query_character = f"""
    SELECT
        CCC.character_id,
        CP.first_message
    FROM `content_chatroom_character` AS CCC
    JOIN `character_persona` AS CP ON CP.character_id = CCC.character_id
    WHERE CCC.chatroom_id = {chatroom_id}
    ORDER BY CCC.created_at
    """
    cursor.execute(query_character)
    characters = cursor.fetchall()
    for c in characters:
        item = {
            "chatroom_id": chatroom_id,
            "timestamp_at": timestamp_at,
            "chatroom_activated_id": chatroom_activated_id,
            "chat": c["first_message"],
            "character_id": c["character_id"]
        }
        dynamodb.put_item(table_name, item)
        timestamp_at += Decimal(0.001)


@preprocessing_cursor
def update_chatroom(
    chatroom_id: int,
    title: str,
    character_ids: list,
    background_name: str,
    background_id: str,
    bgm_id: int = None,
    cursor: object = None
) -> None:
    """컨텐츠에서 사용할 채팅방 수정

    :param chatroom_id: chatroom ID
    :param title: title
    :param character_ids: 채팅방 캐릭터 ID 리스트
    :param background_name: 배경화면 이름
    :param background_id: 배경화면 iD
    :param bgm_id: bgm ID
    :param cursor: pymysql.connect().cursor()
    """
    # 기존 캐릭터 삭제
    query = f"""
    DELETE FROM `content_chatroom_character`
    WHERE chatroom_id = {chatroom_id}
    """
    cursor.execute(query)

    # 새로운 캐릭터 등록
    query_values = []
    for cid in character_ids:
        query_values.append(f"({chatroom_id}, '{cid}')")
    query_values = ", ".join(query_values)
    query = f"""
    INSERT INTO `content_chatroom_character` (chatroom_id, character_id)
    VALUES {query_values}
    """
    cursor.execute(query)

    # 채팅방 정보 수정
    query = """
    UPDATE `content_chatroom`
    SET
        title = %s,
        background_name = %s,
        background_id = %s,
        bgm_id = %s
    WHERE id = %s
    """
    cursor.execute(query, (title, background_name, background_id, bgm_id, chatroom_id))
