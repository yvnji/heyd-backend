import json
import os
import re
import uuid
from boto3.dynamodb.conditions import Key
from decimal import Decimal

import const
from lib import client
from lib import time
from lib.decorator import preprocessing_cursor
from service import avatar as avatar_module
from service import chat as chat_module
from service import reaction as reaction_module
from thirdparty import dynamodb
from thirdparty import lambda_module
from thirdparty import s3
from thirdparty.mariadb import get_db_connection


@preprocessing_cursor
def check_game(game_id: int, cursor: object = None) -> bool:
    """미션게임 ID가 존재하는지 확인

    :param game_id: 미션게임 id
    :param cursor: pymysql.connect().cursor()

    :return
        True: id 존재
        False: id 정보 없음
    """
    sql = "SELECT * FROM `mission_game` WHERE id = %s AND active = 1"
    cursor.execute(sql, (game_id))
    game_data = cursor.fetchone()
    return True if game_data else False


@preprocessing_cursor
def create_chatroom(email: str, meta_id: int, cursor: object = None) -> int:
    """미션게임 채팅방 생성

    :param email: 참여하는 사용자 email
    :param meta_id: 채팅방 메타정보 id
    :param cursor: pymysql.connect().cursor()

    :return: 생성된 채팅방 id
    """
    chat_id = ""

    # 채팅방 생성
    sql = f"""
    INSERT INTO `mission_game_chat`
        (email, meta_id)
    VALUES
        ('{email}', {meta_id})
    RETURNING
        id
    """
    cursor.execute(sql)
    chat_id = cursor.fetchone()["id"]
    print(f"created chat_id : {chat_id}")

    # 채팅방 캐릭터 조회
    sql = f"""
    SELECT character_id
    FROM `mission_game_chat_character`
    WHERE meta_id = {meta_id}
    """
    cursor.execute(sql)
    character_ids = [item["character_id"] for item in cursor.fetchall()]

    # 채팅방 멤버 id 생성
    chatroom_members = chat_module.create_chatroom_member(
        character_ids=character_ids,
        emails=[email],
        game_chat_id=chat_id,
        cursor=cursor,
    )
    print(f"created chatroom members : {chatroom_members}")

    return chat_id


def create_chatroom_meta(
    email: str,
    game_id: int,
    name: str,
    background_file_path: str,
    bgm_file_path: str,
    character_ids: list,
    language: str = "",
) -> int:
    """미션게임 채팅방 메타정보 생성

    :param email: 생성자 email
    :param game_id: game id
    :param name: 채팅방 이름
    :param background_file_path: 배경사진 경로
    :param bgm_file_path: 배경음악 경로
    :param character_ids: 채팅방에 들어가는 character id list (1 ~ 2개)
        [
            '{character_id_1}', '{character_id_2}'
        ]
    :param language: 채팅방 언어

    :return: 생성된 채팅방 메타정보 id
    """
    meta_id = ""
    db_connection = get_db_connection()
    with db_connection as db:
        cursor = db.cursor()

        # 채팅방 메타정보 저장
        sql = """
        INSERT INTO `mission_game_chat_meta`
            (game_id, name, language, bgm_file_path, background_file_path)
        VALUES
            (%s, %s, %s, %s, %s)
        RETURNING
            id
        """
        cursor.execute(
            sql, (game_id, name, language, bgm_file_path, background_file_path)
        )
        meta_id = cursor.fetchone()["id"]

        # 채팅방 캐릭터 설정
        for cid in character_ids:
            sql = f"""
            INSERT INTO `mission_game_chat_character`
                (meta_id, character_id)
            VALUES
                ({meta_id}, '{cid}')
            """
            cursor.execute(sql)

        db.commit()
    return meta_id


def create_game(
    email: str,
    title: str,
    introduce: str,
    thumbnail_file: dict,
    overview: str,
    mission_info: str,
    qa_list: list,
    ending_list: list,
) -> int:
    """미션게임 생성

    :param title: 게임 제목
    :param introduce: 게임 인트로
    :param thumbnail_file: 썸네일 파일 데이터
        {
            'filename': str,  (파일 이름)
            'data': bytes  (파일 데이터)
        }
    :param overview: 게임 개요
    :param mission_info: 미션 정보
    :param qa_list: 미션 질문/답변
        [
            {
                'question': str,
                'answer': str
            },
            ...
        ]
    :param ending_list: 게임 엔딩
        [
            {
                'type': str,  (true | normal | bad)
                'file_path': str,  (엔딩 배경화면 파일 경로)
                'story': str  (엔딩스토리)
            }
        ]

    :return: 생성된 미션게임 id
    """
    game_id = None
    bucket_name = const.S3_BUCKET_NAME[os.environ["AWS_REGION"]][
        os.environ["API_ALIAS"]
    ]

    db_connection = get_db_connection()
    with db_connection as db:
        cursor = db.cursor()

        # 미션게임 데이터 생성
        query = """
        INSERT INTO `mission_game` (title, introduce, overview, mission_info, email)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING id
        """
        cursor.execute(query, (title, introduce, overview, mission_info, email))
        game_id = cursor.fetchone()["id"]

        # 생성된 id를 이름으로 썸네일 파일 S3에 저장
        if thumbnail_file:
            thumbnail_file_name = thumbnail_file["filename"]
            extension = (
                f".{thumbnail_file_name.split('.')[-1]}"
                if "." in thumbnail_file_name
                else ""
            )
            thumbnail_file_path = (
                f"{const.S3_DIRECTORY_GAME_THUMBNAIL}/{game_id}{extension}"
            )
            print(f"PUT s3_bucket_name: {bucket_name}, prefix: {thumbnail_file_path}")
            client.s3_client.put_object(
                Bucket=bucket_name, Key=thumbnail_file_path, Body=thumbnail_file["data"]
            )

            # db에 썸네일 파일 경로 저장
            query = f"""
            UPDATE `mission_game`
            SET thumbnail_file_path = '{thumbnail_file_path}'
            WHERE id = {game_id}
            """
            cursor.execute(query)

        # reaction_target 테이블에 데이터 생성
        query = f"""
        INSERT INTO `reaction_target` (game_id)
        VALUES ({game_id})
        """
        cursor.execute(query)

        # 미션 질문 등록
        query = """
        INSERT INTO `mission_game_question` (game_id, question, answer)
        VALUES (%s, %s, %s)
        """
        for qa in qa_list:
            cursor.execute(query, (game_id, qa["question"], qa["answer"]))

        # 게임 엔딩 등록
        query = """
        INSERT INTO `mission_game_ending` (game_id, image_file_path, story, type)
        VALUES (%s, %s, %s, %s)
        """
        for ending in ending_list:
            cursor.execute(
                query,
                (game_id, ending["image_file_path"], ending["story"], ending["type"]),
            )

        db.commit()
    return game_id


@preprocessing_cursor
def delete_chatroom_meta(meta_id: int, cursor: object = None) -> None:
    """미션게임 채팅방 메타 정보 삭제

    :param meta_id: 메타정보 id
    :param cursor: pymysql.connect().cursor()
    """
    query = f"DELETE FROM `mission_game_chat_meta` WHERE id = {meta_id}"
    cursor.execute(query)


@preprocessing_cursor
def get_chatroom(chat_id: int, cursor: object = None) -> dict:
    """mission_game_chat 테이블 데이터 조회

    :param chat_id: 미션게임 채팅방 id
    :param cursor: pymysql.connect().cursor()

    :return: mission_game_chat row
    """
    query = """
    SELECT
        GC.id,
        GC.created_time,
        GC.modified_time,
        GC.active,
        GC.safe_chat,
        GC.email,
        GC.meta_id,
        GCM.name,
        GCM.language,
        GCM.game_id,
        GCM.bgm_file_path,
        GCM.background_file_path
    FROM
        `mission_game_chat` AS GC
    JOIN
        `mission_game_chat_meta` AS GCM
        ON GC.meta_id = GCM.id
    WHERE
        GC.id = %s
        AND GC.active = 1
    """
    cursor.execute(query, (chat_id))
    return cursor.fetchone()


@preprocessing_cursor
def get_chatroom_info(chat_id: int, cursor: object = None) -> dict:
    """미션게임 채팅방 정보 조회

    :param chat_id: 미션게임 채팅방 id
    :param cursor: pymysql.connect().cursor()

    :return
        {
            'name': str,  (채팅방 이름)
            'bgm_file_path': str,
            'background_file_path: str,
            'language': str,  (채팅방 언어)
            'safe_chat': int,  (safe chat 설정. 1: True, 0: False)
            'members': [
                {
                    'character_id': str,  (채팅방 캐릭터 id)
                    'character_name': str,  (캐릭터 이름)
                    'character_thumbnail_file_path': str,  (캐릭터 썸네일)
                    'avatar_id': str,  (아바타 id)
                    'avatar_thumbnail_file_path': str,  (아바타 썸네일)
                    'avatar_file_path': str,  (아바타 모션 파일 경로)
                    'gender': str,  (아바타 성별 : F or M)
                    'idle_motion_path': str  (처음 감정 모션 파일 경로)
                }
            ]
        }
    """
    # 채팅방 정보 조회
    query = f"""
    SELECT
        GCM.id AS meta_id,
        GCM.name,
        CONCAT('/', GCM.bgm_file_path) AS bgm_file_path,
        CONCAT('/', GCM.background_file_path) AS background_file_path,
        GCM.language,
        GC.safe_chat
    FROM
        `mission_game_chat` AS GC
    JOIN
        `mission_game_chat_meta` AS GCM
        ON GCM.id = GC.meta_id
    WHERE
        GC.id = {chat_id}
        AND active = 1
    """
    cursor.execute(query)
    room = cursor.fetchone()

    # 채팅방 멤버 캐릭터 조회
    if room:
        query = f"""
        SELECT
            C.character_id,
            C.name AS character_name,
            CONCAT('/', C.thumbnail_file_path) AS character_thumbnail_file_path,
            A.avatar_id,
            A.gender,
            CONCAT('/', A.thumbnail_file_path) AS avatar_thumbnail_file_path,
            CONCAT('/', A.avatar_file_path) AS avatar_file_path
        FROM
            `mission_game_chat_character` AS GCC
        LEFT JOIN
            `character` AS C
            ON C.character_id = GCC.character_id
        LEFT JOIN
            `avatar` AS A
            ON C.avatar_id = A.avatar_id
        WHERE
            GCC.meta_id = {room["meta_id"]}
            AND C.active = 1
            AND A.active = 1
        """
        del room["meta_id"]
        cursor.execute(query)
        room["members"] = cursor.fetchall()
        for member in room["members"]:
            # Idle 모션 파일 조회
            member["idle_motion_path"] = "/" + avatar_module.get_emotion_retargeting(
                "Idle", member["avatar_file_path"][1:], member["gender"]
            )
    return room


@preprocessing_cursor
def get_game(game_id: int, email: str, cursor: object = None) -> dict:
    """미션게임 조회

    :param game_id: game id
    :param email: 좋아요, 이모지 확인을 위한 email

    :return
        {
            'game_id': int,
            'title': str,
            'introduce': str,
            'thumbnail_file_path': str,
            'overview': str,
            'mission_info': str,
            'create_username': str,  (게임 생성한 사람 이름)
            'questions': [
                {
                    'question_id': int,
                    'question': str
                },
                ...
            ],
            'like_count': int,  (미션게임 좋아요 수)
            'is_liked': bool,  (email 계정이 이 미션게임을 좋아요 했는지 체크)
            'emojis': [
                {
                    'emoji_id': int,
                    'emoji_type': str (이모지 이름),
                    'count': int (해당 이모지 등록한 수),
                    'is_clicked': bool (email 계정이 해당 이모지를 등록했는지 확인)
                },
                ...
            ],
            'comments': {
                'total': int,  (총 댓글 수)
                'content': str || None,  (좋아요 수가 5개 이상인 댓글 중 가장 높은 댓글)
                'writer': str || None,  (좋아요 수가 5개 이상인 댓글 중 가장 높은 댓글을 등록한 사람 이름)
            }
        }
    """

    data = {}
    query = f"""
    SELECT
        id AS game_id,
        title,
        introduce,
        CONCAT('/', thumbnail_file_path) AS thumbnail_file_path,
        overview,
        mission_info,
        (SELECT name FROM `user` WHERE user.email = mission_game.email) AS create_username
    FROM
        `mission_game`
    WHERE
        id = {game_id}
        AND active = True
    """
    game_target_id = reaction_module.get_reaction_id(game_id=game_id, cursor=cursor)
    cursor.execute(query)
    data = cursor.fetchone()
    data["questions"] = list_questions(game_id, cursor=cursor)
    data["like_count"] = reaction_module.get_like_count(game_target_id, cursor=cursor)
    data["is_liked"] = reaction_module.check_like_by_email(
        game_target_id, email, cursor=cursor
    )
    data["emojis"] = reaction_module.list_emoji_registered(
        game_target_id, email, cursor=cursor
    )
    comments_list = sorted(
        reaction_module.list_comments(game_target_id, email, cursor=cursor),
        key=lambda r: r["like_count"],
        reverse=True,
    )
    data["comments"] = {"total": len(comments_list)}

    # 좋아요 5개 이상인 댓글 조회
    if comments_list and comments_list[0]["like_count"] >= 5:
        comment_at = comments_list[0]
        data["comments"]["content"] = comment_at["content"]
        data["comments"]["writer"] = comment_at["writer"]

    return data


@preprocessing_cursor
def list_chatroom(game_id: int, email: str, cursor: object = None) -> list:
    """미션게임 채팅방 리스트 조회

    :param game_id: game id
    :param email: email
    :param cursor: pymysql.connect().cursor()

    :return
        [
            {
                'game_chat_id': int,
                'language': str,  (채팅방 언어)
                'safe_chat': bool,  (safe chat 설정)
                'name': str,  (채팅방 이름)
                'bgm_file_path': str,
                'background_file_path: str,
                'avatar_list': [
                    {
                        'character_id': str,  (채팅방 캐릭터 id)
                        'avatar_id': str,  (아바타 id)
                        'avatar_thumbnail_file_path': str,  (아바타 썸네일)
                        'avatar_file_path': str,  (아바타 모션 파일 경로)
                        'gender': str  (아바타 성별 : F or M)
                    }
                ]
            }
        ]
    """
    # 채팅방 메타정보 조회
    query = f"""
    SELECT
        id AS meta_id,
        language,
        name,
        CONCAT('/', bgm_file_path) AS bgm_file_path,
        CONCAT('/', background_file_path) AS background_file_path
    FROM
        `mission_game_chat_meta`
    WHERE
        game_id = {game_id}
    """
    cursor.execute(query)
    rooms_meta = cursor.fetchall()

    # 채팅방 조회
    rooms = []
    for meta in rooms_meta:
        query = f"""
        SELECT
            id AS game_chat_id,
            CASE
                WHEN (safe_chat = 1) THEN TRUE
                ELSE FALSE
            END as safe_chat
        FROM
            `mission_game_chat`
        WHERE
            active = 1
            AND meta_id = {meta['meta_id']}
            AND email = '{email}'
        """
        cursor.execute(query)
        room = cursor.fetchone()

        # 채팅방 없을 경우 생성
        if not room:
            room_id = create_chatroom(email, meta["meta_id"], cursor=cursor)
            room = {"game_chat_id": room_id, "safe_chat": 0}

        # 채팅방 아바타 조회
        chat_id = room["game_chat_id"]
        query = f"""
        SELECT
            chatroom_member.character_id,
            avatar_character.avatar_id,
            CONCAT('/', avatar_character.thumbnail_file_path) AS avatar_thumbnail_file_path,
            CONCAT('/', avatar_character.avatar_file_path) AS avatar_file_path,
            avatar_character.gender
        FROM
            `chatroom_member`
        JOIN
            (
                SELECT
                    avatar.thumbnail_file_path,
                    avatar.avatar_id,
                    `character`.character_id,
                    avatar.avatar_file_path,
                    avatar.gender
                FROM
                    `character`
                JOIN
                    `avatar`
                    ON avatar.avatar_id = `character`.avatar_id
            ) AS avatar_character
            ON avatar_character.character_id = chatroom_member.character_id
        WHERE
            chatroom_member.game_chat_id = {chat_id}
            AND chatroom_member.active = 1
        """
        cursor.execute(query)
        room["avatar_list"] = cursor.fetchall()

        del meta["meta_id"]
        room.update(meta)
        rooms.append(room)

    return rooms


def list_chatroom_background() -> list:
    """미션게임 채팅방에 적용 가능한 배경이미지 파일 경로 리스트 조회"""
    file_list = s3.list_files(
        const.S3_BUCKET_NAME[os.environ["AWS_REGION"]][os.environ["API_ALIAS"]],
        const.S3_DIRECTORY_GAME_CHAT_BACKGROUND_DEFAULT,
    )
    return [f"/{file}" for file in file_list]


def list_chatroom_bgm() -> list:
    """미션게임 채팅방에 적용 가능한 bgm 파일 경로 리스트 조회

    :return
        [
            {
                'file_path': str,  (이미지 파일 경로)
                'tag_list': [  (이미지 파일 태그 리스트)
                    'str', ...
                ]
            }
        ]
    """
    ret = []
    img_list = []  # 이미지 파일 경로 리스트
    csv_file = ""  # csv 태그 파일 경로

    # 파일 리스트 조회
    file_list = s3.list_files(
        const.S3_BUCKET_NAME[os.environ["AWS_REGION"]][os.environ["API_ALIAS"]],
        const.S3_DIRECTORY_GAME_CHAT_BGM,
    )
    for file in file_list:
        if file[-3:] == "csv":
            csv_file = file
        else:
            img_list.append(file)

    # 파일 별 태그 조회
    tag_dict = {}
    csv_list = s3.get_object(
        const.S3_BUCKET_NAME[os.environ["AWS_REGION"]][os.environ["API_ALIAS"]],
        csv_file,
    ).split("\n")[1:]
    for row in csv_list:
        _, name, tag = row.split(",")
        name = name.replace("'", "_")
        tag_dict[name] = tag.strip("#").strip().replace(" ", "").split("#")

    for img_path in img_list:
        img_name = img_path.split("/")[1][4:-4]
        ret.append({"file_path": f"/{img_path}", "tag_list": tag_dict[img_name]})
    return ret


def list_games(email: str, page_size: int, offset: int) -> list:
    """홈화면에서 미션게임 리스트 조회

    :return
        [
            {
                'game_id': int,
                'title': str,
                'introduce': str,
                'thumbnail_file_path: str,
                'create_username': str,
                'liked_count': int,
                'is_liked': bool,
                'mission_info': str
            },
            ...
        ]
    """

    data = []
    query = f"""
    SELECT
        mission_game.id AS game_id,
        mission_game.title,
        mission_game.introduce,
        CONCAT('/', mission_game.thumbnail_file_path) AS thumbnail_file_path,
        mission_game.mission_info,
        user.name AS create_username,
        reaction_target.id AS target_id
    FROM
        `mission_game`
    JOIN
        `user`
        ON user.email = mission_game.email
    JOIN
        `reaction_target`
        ON reaction_target.game_id = mission_game.id
    WHERE
        mission_game.active = 1
    ORDER BY created_time DESC
    LIMIT {page_size} OFFSET {offset}
    """
    db_connection = get_db_connection()
    with db_connection as db:
        cursor = db.cursor()
        cursor.execute(query)
        data = cursor.fetchall()
        for d in data:
            d["is_liked"] = reaction_module.check_like_by_email(
                d["target_id"], email, cursor=cursor
            )
            d["liked_count"] = reaction_module.get_like_count(
                d["target_id"], cursor=cursor
            )
            del d["target_id"]
    return data


def list_previous_chat(chat_id: int, last_evaluated_key: dict = None) -> dict:
    """미션게임 채팅방 이전 채팅 내용 조회

    :param chat_id: 채팅방 id
    :param last_evaluated_key: DynamoDB 'idolmaster_game_chat' 데이터 리스트의 마지막 데이터 키

    :return
        {
            'chats': [
                {
                    'chat_id': int,  (채팅 id)
                    'send_time': str,  (보낸 시간)
                    'email': str,  (사용자 email. 사용자가 보낸 경우만 존재)
                    'character_id': str,  (캐릭터 id, 캐릭터가 보낸 경우만 존재)
                    'msg': str  (메세지 내용)
                }
            ],
            'last_evaluated_key': {
                'chat_id': int,  (채팅방 id),
                'send_time': str  (메세지 보낸 시간)
            }
        }
    """

    # DynamoDB에서 이전 채팅 내용 조회
    table_name = "idolmaster_game_chat"
    chat_list_pre, last_evaluated_key = dynamodb.fetch_data_query(
        table_name,
        Key("chat_id").eq(chat_id),
        limit=50,
        index_forward=False,
        last_evaluated_key=last_evaluated_key,
    )

    # 시간 순으로 인덱스 정렬
    chat_list_pre = chat_list_pre[::-1]

    # 만약 채팅이 없을 경우 캐릭터의 첫 메세지 추가
    if not len(chat_list_pre):
        db_connection = get_db_connection()
        with db_connection as db:
            cursor = db.cursor()
            query = f"""
            SELECT
                chatroom_member.email,
                `user`.nickname,
                chatroom_member.character_id,
                `character`.name,
                character_persona.first_message
            FROM
                `chatroom_member`
            LEFT JOIN
                `user`
                ON `user`.email = chatroom_member.email
            LEFT JOIN
                `character`
                ON `character`.character_id = chatroom_member.character_id
            LEFT JOIN
                `character_persona`
                ON character_persona.character_id = chatroom_member.character_id
            WHERE
                chatroom_member.game_chat_id = {chat_id}
            """
            cursor.execute(query)
            results = cursor.fetchall()
            print(results)

            timestamp_at = str(round(Decimal(time.timestampnow()), 5))
            chat = {"chat_id": chat_id, "send_time": timestamp_at}
            user_name = ""
            for res in results:
                if res.get("email"):
                    user_name = res["nickname"]
                elif res.get("character_id") and not chat.get("msg"):
                    chat["id"] = res["character_id"]
                    chat["msg"] = (
                        res["first_message"]
                        .replace("{{user}}", user_name)
                        .replace("{{character}}", res["name"])
                    )
            dynamodb.put_item(table_name, chat)
            chat_list_pre.append(chat)

            query = f"""
            UPDATE `chatroom_member`
            SET last_send_time = '{timestamp_at}'
            WHERE game_chat_id = {chat_id} AND character_id = '{chat['id']}'
            """
            cursor.execute(query)
            db.commit()
    return {"chats": chat_list_pre, "last_evaluated_key": last_evaluated_key}


@preprocessing_cursor
def list_questions(game_id: str, cursor: object = None) -> list:
    """미션게임 질문 리스트 조회

    :return
        [
            {
                'question_id': int,
                'question': str
            },
            ...
        ]
    """
    questions = []
    query = f"""
    SELECT
        id as question_id,
        question
    FROM
        `mission_game_question`
    WHERE
        game_id = {game_id}
    """
    cursor.execute(query)
    questions = cursor.fetchall()
    return questions


@preprocessing_cursor
def remove_chatroom(chat_id: int, cursor: object = None) -> None:
    """사용자 미션게임 채팅방 비활성화

    :param chat_id: 채팅방 id
    :param cursor: pymysql.connect().cursor()
    """
    query = f"UPDATE `mission_game_chat` SET active = 0 WHERE id = {chat_id}"
    cursor.execute(query)


def submit_mission(game_id: int, answers: list) -> dict:
    """미션 응답 제출

    :param game_id: 미션게임 Id
    :param answers: 미션 질문에 대한 응답
        [
            {
                'question_id': int,
                'answer': str
            },
            ...
        ]

    :return: 답변 점수에 따른 엔딩
        {
            'story': str,  (엔딩 텍스트)
            'type': str,  (true | normal | bad)
            'image_file_path': str
        }
    """
    db_connection = get_db_connection()
    with db_connection as db:
        cursor = db.cursor()

        # 정답 조회
        query = f"""
        SELECT
            id, answer
        FROM
            `mission_game_question`
        WHERE
            game_id = {game_id}
        """
        cursor.execute(query)
        answer_list = cursor.fetchall()
        answer_dict = {a["id"]: a["answer"] for a in answer_list}

        # LLM 적용
        lambda_function = "idolmaster-mission-scroe-llm-chatgpt4-mini-api"
        prompt = (
            "Correct Answer\nA1 : {%s}\nA2 : {%s}\nA3 : {%s}\n\nUser’s Answer\nA1 : {%s}\nA2 : {%s}\nA3 : {%s}"
            % (
                answer_dict[answers[0]["question_id"]],
                answer_dict[answers[1]["question_id"]],
                answer_dict[answers[2]["question_id"]],
                answers[0]["answer"],
                answers[1]["answer"],
                answers[2]["answer"],
            )
        )
        print("prompt : %s" % prompt)
        response = lambda_module.invoke(
            lambda_function,
            {"prompt": prompt},
            use_alias=True
        )["Payload"]
        print("response :", response)
        answer_score = json.loads(response["body"])["answer"]
        pattern = r"(\d+\.?\d*)\s+points"
        points = re.findall(pattern, answer_score)  # 대답에 대한 점수 [a1, a2, a3, avg]
        print("score :", points)
        point_avg = Decimal(points[-1])

        # Ending type by score
        if 8 <= point_avg <= 10:
            ending_type = const.MISSION_ENDING_TRUE
        elif 5 <= point_avg < 8:
            ending_type = const.MISSION_ENDING_NORMAL
        elif 1 <= point_avg < 5:
            ending_type = const.MISSION_ENDING_BAD
        else:
            raise Exception(f"Invalid ending point : {point_avg}")

        ending = {}
        query = f"""
        SELECT
            story,
            type,
            CONCAT('/', image_file_path) AS image_file_path
        FROM
            `mission_game_ending`
        WHERE
            game_id = {game_id}
            AND type = '{ending_type}'
        """
        cursor.execute(query)
        ending = cursor.fetchone()
    return ending


def upload_chatroom_background(image_file: dict) -> str:
    """게임 채팅방 배경화면 파일 S3에 저장

    :param image_file: 배경 파일 데이터
        {
            'filename': str,  (파일 이름)
            'data': bytes  (파일 데이터))
        }

    :return: S3에 저장된 파일 경로
    """
    uid = str(uuid.uuid4())
    image_file_name = image_file["filename"]
    extension = f".{image_file_name.split('.')[-1]}" if "." in image_file_name else ""
    created_name = uid + extension
    image_file_path = f"{const.S3_DIRECTORY_GAME_CHAT_BACKGROUND}/{created_name}"
    s3.upload_file(image_file_path, image_file["data"])
    return "/" + image_file_path


def upload_ending_background(image_file: dict) -> str:
    """게임 엔딩 배경화면 파일 S3에 저장

    :param image_file: 엔딩 배경 파일 데이터
        {
            'filename': str,  (파일 이름)
            'data': bytes  (파일 데이터))
        }

    :return: S3에 저장된 파일 경로
    """
    uid = str(uuid.uuid4())
    image_file_name = image_file["filename"]
    extension = f".{image_file_name.split('.')[-1]}" if "." in image_file_name else ""
    created_name = uid + extension
    image_file_path = f"{const.S3_DIRECTORY_GAME_ENDING_IMAGE}/{created_name}"
    s3.upload_file(image_file_path, image_file["data"])
    return "/" + image_file_path
