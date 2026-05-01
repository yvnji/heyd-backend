from datetime import datetime, timezone
from decimal import Decimal
import json

import shortuuid
from boto3.dynamodb.conditions import Key, Attr

from lib import time
from lib.decorator import preprocessing_cursor
from service import avatar as avatar_module
from service import character as character_module
from service import chatroom as chatroom_module
from thirdparty import dynamodb
from thirdparty import s3
from thirdparty.mariadb import get_db_connection


@preprocessing_cursor
def check_active(chat_id: str, cursor: object = None) -> bool:
    """채팅방의 활성화 상태를 확인

    :param chat_id: 채팅방 id
    :param cursor: pymysql.connect().cursor()

    :return
        True: 현재 채팅방 활성화
        False: 현재 채팅방 비활성화 or 존재하지 않음
    """
    cursor.execute(
        """
        SELECT 'chat' AS type, chat_id AS id FROM `chat` WHERE chat_id = %s AND active = 1 UNION
        SELECT 'groupchat' AS type, groupchat_id AS id FROM `groupchat` WHERE groupchat_id = %s AND active = 1
    """,
        (chat_id, chat_id),
    )
    result = cursor.fetchone()
    return True if result else False


def check_chatroom(email: str, character_id: str):
    data = {"is_existence": False, "chatroom_id": None}

    db_connection = get_db_connection()
    with db_connection.cursor() as cursor:
        sql = """
        SELECT chat_id
        FROM `chat_member`
        WHERE
            chat_id IN (
                SELECT chat_id
                FROM `chat_member`
                WHERE member_id = %s AND active = TRUE
            )
            AND chat_id IN (
                SELECT chat_id
                FROM `chat_member`
                WHERE member_id = %s
            )
            AND active = TRUE
            AND EXISTS (
                SELECT 1
                FROM `chat`
                WHERE chat.chat_id = chat_member.chat_id AND chat.active = TRUE
            )
        """
        cursor.execute(
            sql,
            (
                email,
                character_id,
            ),
        )
        result = cursor.fetchone()

        if result:
            data["is_existence"] = True
            data["chatroom_id"] = result["chat_id"]

    return data


@preprocessing_cursor
def check_member(email: str, chat_id: str, cursor: object = None) -> bool:
    """email 사용자가 chat_id 채팅방 멤버인지 확인

    :param email: 사용자 email
    :param chat_id: 채팅방 id
    :param cursor: pymysql.connect().cursor()

    :return
        True: 채팅방 멤버 O
        False: 채팅방 멤버 X
    """
    cursor.execute(
        """
        SELECT 'chat' AS type FROM `chat_member` WHERE active = 1 AND chat_id = %s AND member_id = %s UNION
        SELECT 'groupchat' AS type FROM `groupchat_member`
        WHERE active = 1 AND groupchat_id = %s AND member_id = %s
    """,
        (chat_id, email, chat_id, email),
    )
    result = cursor.fetchone()
    return True if result else False


def create_chatroom(email: str, character_id: str, language: str):
    # chatroom 정보
    uuid = shortuuid.ShortUUID().random(length=20)
    timestamp_at = str(round(Decimal(time.timestampnow()), 5))
    db_connection = get_db_connection()
    with db_connection.cursor() as cursor:
        chatroom_sql = "INSERT INTO `chat` (`chat_id`, `active`, `language`, `safe_chat`) VALUES (%s, %s, %s, %s)"
        cursor.execute(chatroom_sql, (uuid, True, language, False))

        chatroom_user_sql = "INSERT INTO `chat_member` (`chat_id`, `member_id`, `active`, `notification`, `last_send_time`, `is_user`) VALUES (%s, %s, %s, %s, %s, %s)"
        cursor.execute(chatroom_user_sql, (uuid, email, True, True, timestamp_at, True))

        chatroom_char_sql = "INSERT INTO `chat_member` (`chat_id`, `member_id`, `active`, `notification`, `last_send_time`, `is_user`) VALUES (%s, %s, %s, %s, %s, %s)"
        cursor.execute(
            chatroom_char_sql, (uuid, character_id, True, False, timestamp_at, False)
        )

        # 추리게임 step 삽입
        cursor.execute(
            "SELECT COUNT(*) as game_exists FROM `guessing_game` WHERE character_id = %s",
            (character_id,),
        )
        guessing_game_result = cursor.fetchone()
        if guessing_game_result and guessing_game_result["game_exists"]:
            guessing_game_step_sql = """
            INSERT INTO `guessing_game_step` (`chat_id`, `current_step`)
            VALUES (%s, %s)
            """
            cursor.execute(guessing_game_step_sql, (uuid, "Introduction"))

    db_connection.commit()
    db_connection.close()

    return uuid


@preprocessing_cursor
def create_chatroom_member(
    character_ids: list = [],
    emails: list = [],
    chat_id: str = None,
    game_chat_id: str = None,
    groupchat_id: int = None,
    cursor: object = None,
) -> list:
    """chatroom_member 테이블에 member 등록

    :param character_ids: 캐릭터 id 리스트
    :param emails: 계정 email 리스트
    :param chat_id: 채팅방 id
    :param game_chat_id: 미션게임 채팅방 id
    :param groupchat_id: 그룹채팅방 id
    :param cursor: pymysql.connect().cursor()

    :return: 생성된 chatroom_member 데이터 리스트
    """

    # 제약 조건
    if sum(
        cid is not None for cid in [chat_id, game_chat_id, groupchat_id]
    ) != 1 or not (character_ids + emails):
        raise Exception(
            "invalid resources chat.create_chatroom_member (params : {locals()})"
        )

    chatroom_members = []
    insert_key_value = {}
    target_id_key = ""
    target_id_value = ""
    timestamp_at = str(round(Decimal(time.timestampnow()), 5))

    if chat_id:
        target_id_key = "chat_id"
        target_id_value = f"'{chat_id}'"
    elif game_chat_id:
        target_id_key = "game_chat_id"
        target_id_value = f"{game_chat_id}"
    elif groupchat_id:
        target_id_key = "groupchat_id"
        target_id_value = f"'{groupchat_id}'"

    if emails:
        key = f"({target_id_key}, email, last_send_time)"
        insert_key_value[key] = []
        for email in emails:
            value = f"({target_id_value}, '{email}', '{timestamp_at}')"
            insert_key_value[key].append(value)
    if character_ids:
        key = f"({target_id_key}, character_id, notification, last_send_time)"
        insert_key_value[key] = []
        for character_id in character_ids:
            value = f"({target_id_value}, '{character_id}', 0, '{timestamp_at}')"
            insert_key_value[key].append(value)

    for key in insert_key_value:
        values_query = ", ".join(insert_key_value[key])
        query = f"INSERT INTO `chatroom_member` {key} VALUES {values_query} RETURNING *"
        cursor.execute(query)
        chatroom_members.append(cursor.fetchone())

    return chatroom_members


def delete_evaluate_chat(email: str, chatroom_id: str, send_time: str):
    db_connection = get_db_connection()
    with db_connection.cursor() as cursor:
        cursor.execute(
            "SELECT * FROM `chat_message_evaluate` WHERE chat_id = %s AND message_send_time = %s AND email = %s",
            (chatroom_id, send_time, email),
        )
        chat_evaluation = cursor.fetchone()

        if chat_evaluation:
            cursor.execute(
                "DELETE FROM `chat_message_evaluate` WHERE chat_id = %s AND message_send_time = %s AND email = %s",
                (chatroom_id, send_time, email),
            )

    db_connection.commit()
    db_connection.close()


def get_chat_evaluation(email: str, chatroom_id: str, send_time: str):
    like = None
    db_connection = get_db_connection()
    with db_connection.cursor() as cursor:
        cursor.execute(
            "SELECT * FROM `chat_message_evaluate` WHERE chat_id = %s AND message_send_time = %s AND email = %s",
            (chatroom_id, send_time, email),
        )
        chat_evaluation = cursor.fetchone()
        if chat_evaluation:
            like = bool(chat_evaluation["like_value"])

    return like


def get_chatroom_info(email: str, chatroom_id: str):
    returncode = 0
    chatroom_info = {
        "room_type": "personal",
        "title": "",
        "language": "",
        "members": [],
        "avatarInfo": [],
        "notification_on": None,
        "safe_chat": None,
        # "build_url": None
    }
    s3_asset_cf_domain = ""

    # 사용자 존재 여부 검증
    db_connection = get_db_connection()
    with db_connection.cursor() as cursor:
        sql = """
        SELECT C.`language`, C.`safe_chat`, CM.*,
        (SELECT concat(pose, ';', build_file_path) FROM `3dviewer_background` AS VB WHERE persons = 1 order by rand() LIMIT 1) AS build_url_pose,
        (SELECT nickname FROM `user` WHERE `email` = CM.member_id AND active = TRUE) AS nickname,
        (SELECT concat(Cha.thumbnail_file_path, ';', Cha.name, ';', A.avatar_file_path)
                    FROM `character` as Cha, `avatar` as A
                    WHERE Cha.character_id = CM.member_id AND A.avatar_id = Cha.avatar_id AND Cha.active = TRUE) AS character_info
        FROM `chat_member` as CM, `chat` as C
        WHERE C.`chat_id` = %s AND CM.`chat_id` = C.`chat_id` AND C.active = TRUE AND CM.active = TRUE
        """
        cursor.execute(sql, (chatroom_id))
        chatroom_result = cursor.fetchall()

        # 채팅방 정보 가져오기 =======================================

        if chatroom_result:
            chatroom_info["language"] = chatroom_result[0]["language"]
            chatroom_info["safe_chat"] = bool(chatroom_result[0]["safe_chat"])
            # build_url_pose = chatroom_result[0]["build_url_pose"].split(';')
            # pose = build_url_pose[0]
            # build_url = build_url_pose[1]
            # build_files = {
            #     "Build.data.gz": build_url + "Build.data.gz",
            #     "Build.framework.js.gz": build_url + "Build.framework.js.gz",
            #     "Build.loader.js": build_url + "Build.loader.js",
            #     "Build.wasm.gz": build_url + "Build.wasm.gz"
            # }
            # chatroom_info["build_url"] = build_files

            for chatroom_member in chatroom_result:
                members_map = {}
                members_map["id"] = chatroom_member["member_id"]

                if chatroom_member["is_user"] is True:
                    # 사용자가 존재하지 않을 경우
                    if chatroom_member["member_id"] != email:
                        return {
                            "result": 0,
                            "message": "The user does not have access right for this chatroom.",
                        }
                    members_map["name"] = chatroom_member["nickname"]
                    chatroom_info["notification_on"] = bool(
                        chatroom_member["notification"]
                    )

                else:
                    avatar_map = {}

                    character_info = chatroom_member["character_info"].split(";")
                    character = {}
                    character["thumbnail_file_path"] = character_info[0]
                    character["name"] = character_info[1]
                    character["model_file_path"] = character_info[2]

                    members_map["name"] = character["name"]
                    chatroom_info["title"] = character["name"]
                    members_map["thumbnail_url"] = (
                        s3_asset_cf_domain + "/" + character["thumbnail_file_path"]
                    )
                    avatar_map["url"] = s3.get_s3_file_path_temp(
                        character["avatar_file_path"], 3600, False
                    )
                    avatar_map["id"] = chatroom_member["member_id"]
                    # avatar_map["pose"] = pose
                    chatroom_info["avatarInfo"].append(avatar_map)

                chatroom_info["members"].append(members_map)

            # TODO
            returncode = 1
        else:
            returncode = 0
        # # 3D background
        # response = s3.list_objects_v2(Bucket="idolmaster-asset", Prefix="background/")
        # files = [obj["Key"] for obj in response.get("Contents", [])]
        # if not files:
        #     return None
        # selected_file = random.choice(files)
        # background_file_url = gets3file(selected_file, 3600, False)

    return {"result": returncode, "data": chatroom_info}


def get_chatroom_info_v2(email: str, chatroom_id: str):
    s3_asset_cf_domain = ""
    chatroom_info = {}

    # 사용자 존재 여부 검증
    db_connection = get_db_connection()
    with db_connection.cursor() as cursor:
        sql = """
        SELECT
            C.`language`,
            C.`safe_chat`,
            CM.*,
            (
                SELECT
                    concat(pose, ';', build_file_path)
                FROM
                    `3dviewer_background` AS VB
                WHERE
                    persons = 1
                order by rand()
                LIMIT 1
            ) AS build_url_pose,
            (
                SELECT
                    nickname
                FROM
                    `user`
                WHERE
                    `email` = CM.member_id
                    AND active = TRUE
            ) AS nickname,
            (
                SELECT
                    concat(Cha.thumbnail_file_path, ';', Cha.name, ';', A.avatar_file_path, ';', Cha.type, ';', Cha.description, ';', A.gender)
                FROM
                    `character` as Cha,
                    `avatar` as A
                WHERE
                    Cha.character_id = CM.member_id
                    AND A.avatar_id = Cha.avatar_id
                    AND Cha.active = TRUE
            ) AS character_info,
            GG.briefing, GG.casenote, GG.background_path,
            GGS.current_step
        FROM `chat_member` as CM
        JOIN
            `chat` as C ON C.`chat_id` = CM.`chat_id`
        LEFT JOIN
            `guessing_game` AS GG ON GG.character_id = CM.member_id
        LEFT JOIN
            `guessing_game_step` AS GGS ON GGS.chat_id = CM.chat_id
        WHERE
            C.`chat_id` = %s
            AND C.active = TRUE
            AND CM.active = TRUE
        """
        cursor.execute(sql, (chatroom_id,))
        chatroom_result = cursor.fetchall()

        # 채팅방 정보 가져오기 =======================================

        if chatroom_result:
            chatroom_info = {
                "room_type": "",  # "group", "mystery", "concept", "user", "preset", "celeb"
                "title": "",
                "language": "",
                "members": [],
                "avatarInfo": [],
                "notification_on": None,
                "safe_chat": False,
                # "build_url": None
            }
            chatroom_info["language"] = chatroom_result[0]["language"]
            chatroom_info["safe_chat"] = bool(chatroom_result[0]["safe_chat"])
            # build_url_pose = chatroom_result[0]["build_url_pose"].split(';')
            # pose = build_url_pose[0]
            # build_url = build_url_pose[1]
            # build_files = {
            #     "Build.data.gz": build_url + "Build.data.gz",
            #     "Build.framework.js.gz": build_url + "Build.framework.js.gz",
            #     "Build.loader.js": build_url + "Build.loader.js",
            #     "Build.wasm.gz": build_url + "Build.wasm.gz"
            # }
            # chatroom_info["build_url"] = build_files

            for chatroom_member in chatroom_result:
                members_map = {}
                members_map["id"] = chatroom_member["member_id"]

                if bool(chatroom_member["is_user"]) is True:
                    members_map["name"] = chatroom_member["nickname"]
                    chatroom_info["notification_on"] = bool(
                        chatroom_member["notification"]
                    )

                else:
                    avatar_map = {}

                    if chatroom_member["character_info"]:
                        # 캐릭터 파일들(모션, 썸네일) 존재 확인
                        character_module.check_file_path(
                            chatroom_member["member_id"], cursor=cursor
                        )

                        character_info_data = chatroom_member["character_info"].split(
                            ";"
                        )

                        chatroom_info["room_type"] = character_info_data[3]
                        chatroom_info["title"] = character_info_data[1]

                        members_map["name"] = character_info_data[1]
                        members_map["thumbnail_url"] = (
                            s3_asset_cf_domain + "/" + character_info_data[0]
                        )

                        avatar_map["url"] = (
                            s3_asset_cf_domain + "/" + character_info_data[2]
                        )
                        avatar_map["id"] = chatroom_member["member_id"]
                        avatar_map["gender"] = character_info_data[5]
                        avatar_map["idle_motion_path"] = (
                            "/"
                            + avatar_module.get_emotion_retargeting(
                                "Idle", character_info_data[2], character_info_data[5]
                            )
                        )
                        # avatar_map["pose"] = pose
                        chatroom_info["avatarInfo"].append(avatar_map)

                        if chatroom_info["room_type"] == "mystery":
                            chatroom_info["title"] = character_info_data[4]
                            chatroom_info["assistant_line"] = chatroom_member[
                                "briefing"
                            ].split(";")
                            chatroom_info["case_note"] = json.loads(
                                chatroom_member["casenote"]
                            )

                            avatar_map = {}
                            robot_motion = "guessing_game/avatar/robot_ava_action.glb"
                            avatar_map["url"] = s3_asset_cf_domain + "/" + robot_motion
                            avatar_map["id"] = "robot"
                            # avatar_map["idle_motion_path"] = (
                            #     "/"
                            #     + avatar_module.get_emotion_retargeting(
                            #         "Idle", robot_motion
                            #     )
                            # )
                            avatar_map["idle_motion_path"] = "/" + robot_motion
                            chatroom_info["avatarInfo"].append(avatar_map)

                            chatroom_info["step"] = chatroom_member["current_step"]

                            background_info = [
                                {
                                    "id": "robot",
                                    "url": "/guessing_game/background_image/background_briefing2.jpg",  # 브리핑룸2 고정
                                },
                                {
                                    "id": "character",
                                    "url": chatroom_member[
                                        "background_path"
                                    ],  # 닥터첸: 닥터첸 배경, 땅콩살인: 브리핑룸1
                                },
                            ]
                            chatroom_info["background_url"] = background_info
                        else:
                            background_info = [
                                {"id": "character", "url": "/background/normal/.jpg"}
                            ]
                            chatroom_info["background_url"] = background_info

                chatroom_info["members"].append(members_map)

    return chatroom_info


def get_previous_chat(
    email: str, chatroom_id: str, last_evaluated_key: dict, limit: int = 50
):
    # 이전 chat 내용 가져오기
    table_name = "idolmaster_chat"

    # 두 번째 호출부터: 다음 50개 항목 가져오기
    previous_chat, last_evaluated_key = dynamodb.fetch_data_query(
        table_name,
        Key("chatroom_uuid").eq(chatroom_id),
        limit=limit,
        index_forward=False,  # 내림차순
        last_evaluated_key=last_evaluated_key,
    )

    # 오름차순으로 정렬
    previous_chat.sort(key=lambda x: x["send_time"])

    # 만약 채팅이 없을 경우 캐릭터의 첫 메세지 추가
    if len(previous_chat) == 0:
        db_connection = get_db_connection()
        with db_connection.cursor() as cursor:
            sql = """
            SELECT A.member_id, per.first_message, B.name, (SELECT nickname FROM `user` WHERE email = %s ) AS nickname
            FROM `chat_member` AS A, `character`AS B, `character_persona` AS per
            WHERE A.`chat_id`= %s AND A.member_id = B.character_id AND per.character_id = B.character_id
            """
            cursor.execute(sql, (email, chatroom_id))
            result = cursor.fetchone()

            timestamp_at = str(round(Decimal(time.timestampnow()), 5))

            if result:
                chat = {
                    "chatroom_uuid": chatroom_id,
                    "id": result["member_id"],
                    "msg": result["first_message"]
                    .replace("{{user}}", result["nickname"])
                    .replace("{{character}}", result["name"]),
                    "send_time": timestamp_at,
                }
                dynamodb.put_item(table_name, chat)
                previous_chat.append(chat)

            cursor.execute(
                "UPDATE `chat_member` SET `last_send_time` = %s WHERE `chat_id` = %s AND `member_id` = %s ",
                (timestamp_at, chatroom_id, result["member_id"]),
            )
        db_connection.commit()
        db_connection.close()

    return {"chats": previous_chat, "last_evaluated_key": last_evaluated_key}


def leave_chatroom(email: str, chatroom_id: str):
    db_connection = get_db_connection()
    with db_connection.cursor() as cursor:
        sql = "UPDATE `chat` SET `active` = %s WHERE `chat_id` = %s"
        cursor.execute(sql, (False, chatroom_id))

        sql = "UPDATE `chat_member` SET `active` = %s WHERE `chat_id` = %s"
        cursor.execute(sql, (False, chatroom_id))

        # 추리게임 step 삽입
        cursor.execute(
            "SELECT COUNT(*) as game_exists FROM `guessing_game_step` WHERE chat_id = %s",
            (chatroom_id,),
        )
        guessing_game_result = cursor.fetchone()
        if guessing_game_result and guessing_game_result["game_exists"]:
            guessing_game_step_sql = """
            DELETE FROM `guessing_game_step` WHERE `chat_id` = %s
            """
            cursor.execute(guessing_game_step_sql, (chatroom_id))

    db_connection.commit()
    db_connection.close()


@preprocessing_cursor
def list_chat_histories_content(content_id: int, chatroom_id: int, user_id: int = None, only_user: bool = False, cursor: object = None) -> list:
    """채팅방 컨텐츠의 채팅내역 조회

    :param content_id: 컨텐츠 ID
    :param chatroom_id: 컨텐츠에 등록되어 있는 채팅방 ID (Table : content_chatroom)
    :param user_id: 사용자 ID (값이 없을 경우 해당 컨텐츠를 사용한 모든 사용자의 채팅방 조회)
    :param only_user: 채팅 종류
        True: 사용자 채팅만 조회
        False: 사용자, AI 채팅 모두 조회
    :param cursor: pymysql.connect().cursor()

    :return
    """
    chat_tb = dynamodb.get_resource_obj("idolmaster_content_chat")
    scan_condition = None
    if user_id:
        chatroom_activated = chatroom_module.get_chatroom_activated(user_id, content_id=content_id, cursor=cursor)
        if chatroom_activated:
            scan_condition = Key("chatroom_activated_id").eq(chatroom_activated["id"])
        else:
            return []
    if only_user:
        if scan_condition:
            scan_condition &= Attr("user_id").exists()
        else:
            scan_condition = Attr("user_id").exists()
    return dynamodb.query_all_items(
        chat_tb,
        Key("chatroom_id").eq(chatroom_id),
        scan_condition=scan_condition,
        index_forward=False   # 채팅 시간 내림차순
    )


def list_chatroom(email: str, page_size: int, offset: int):
    query = f"""
    SELECT *
    FROM (
        SELECT chat_id, 'chat' AS room_type,
        (SELECT MAX(last_send_time) FROM `chat_member` AS A WHERE A.chat_id = B.chat_id ) as last_send_time, notification,
        2  AS count_member,
        (SELECT concat(NAME, ';', thumbnail_file_path) FROM `character` WHERE active = TRUE AND character_id = B.member_id) AS character_info,
        '' AS chat_info
        FROM (SELECT * FROM `chat_member` WHERE chat_id in (SELECT chat_id FROM `chat_member` WHERE member_id = "{email}" AND active = TRUE) AND is_user = FALSE) AS B
        WHERE EXISTS (SELECT 1 FROM `chat` WHERE chat.chat_id = B.chat_id AND chat.active = TRUE)

        UNION ALL

        SELECT groupchat_id, 'groupchat' AS room_type,
        (SELECT MAX(last_send_time) FROM `groupchat_member` AS A WHERE A.groupchat_id = B.groupchat_id ) as last_send_time, notification,
        (
            SELECT COUNT(*)
            FROM `groupchat_member` AS A
            WHERE A.groupchat_id = B.groupchat_id
            AND A.active = TRUE
            AND A.member_id NOT IN (
                SELECT character_id
                FROM `character_block`
                WHERE email = "{email}"
            )
            AND A.member_id NOT IN (
                SELECT C.character_id
                FROM `character` AS C
                JOIN `user_block` AS CRB ON C.email = CRB.blocked_email
                WHERE CRB.email = "{email}"
            )
        ) AS count_member,
        '',
        (SELECT concat(NAME, ';', email) FROM `groupchat` WHERE groupchat_id = B.groupchat_id)
        FROM (SELECT  distinct groupchat_id, notification, is_user FROM `groupchat_member` WHERE groupchat_id in (SELECT groupchat_id FROM `groupchat_member` WHERE member_id = "{email}" AND active = TRUE) AND is_user = FALSE) AS B
        # WHERE EXISTS (SELECT 1 FROM `groupchat` WHERE groupchat.groupchat_id = B.groupchat_id AND groupchat.active = TRUE)
    ) AS combined_chats
    ORDER BY last_send_time DESC
    LIMIT %s OFFSET %s
    """
    chatroom_info_list = []
    s3_asset_cf_domain = ""
    db_connection = get_db_connection()
    with db_connection.cursor() as cursor:
        cursor.execute(query, (page_size, offset))
        chatroom_list = cursor.fetchall()

        if chatroom_list:
            chat_tb = dynamodb.get_resource_obj("idolmaster_chat")
            groupchat_tb = dynamodb.get_resource_obj("idolmaster_groupchat")

            for room in chatroom_list:
                room_info = {
                    "chatroom_uuid": "",
                    "title": "",
                    "total_member": 0,
                    "ai_thumbnails": [],
                    "latest_chat": "",
                    "latest_chat_time": "",
                    "group": False,
                    "is_owner": False,
                    "notification_on": room["notification"],
                }
                # 1대1
                if room["room_type"] == "chatroom":
                    room_info["chatroom_uuid"] = room["chat_id"]
                    room_info["total_member"] = room["count_member"]
                    # cursor.execute("SELECT name, thumbnail_file_path FROM `character` WHERE active = True AND uuid = (SELECT member_id FROM `chatroom_member` WHERE is_user = False AND active = True AND uuid = %s)", (room["uuid"],))
                    # character_info = cursor.fetchone()
                    # if character_info:
                    #     room_info["title"] = character_info["name"]
                    #     room_info["ai_thumbnails"].append(s3_asset_cf_domain + "/" + character_info["thumbnail_file_path"])

                    character_info = (
                        room["character_info"].split(";")
                        if room["character_info"]
                        else None
                    )
                    if character_info:
                        room_info["title"] = character_info[0]
                        room_info["ai_thumbnails"].append(
                            s3_asset_cf_domain + "/" + character_info[1]
                        )

                    # chatroom chat 정보 가져오기
                    latest_chat = chat_tb.query(
                        KeyConditionExpression=Key("chatroom_uuid").eq(room["chat_id"])
                        & Key("send_time").eq(room["last_send_time"])
                    )["Items"]
                    if latest_chat:
                        room_info["latest_chat"] = latest_chat[0]["msg"]
                        room_info["latest_chat_time"] = latest_chat[0]["send_time"]

                    chatroom_info_list.append(room_info)

                # 그룹챗
                elif room["room_type"] == "groupchat":
                    room_info["chatroom_uuid"] = room["chat_id"]
                    room_info["group"] = True
                    # cursor.execute("SELECT name, owner_id FROM `groupchat` WHERE uuid = %s AND active = TRUE", (room["uuid"]))
                    # groupchat_info = cursor.fetchone()
                    # room_info['title'] = groupchat_info['name']
                    # room_info['total_member'] = room['count_member']
                    # room_info['is_owner'] = True if groupchat_info['owner_id'] == email else False

                    chat_info = room["chat_info"].split(";")

                    room_info["title"] = chat_info[0]
                    room_info["total_member"] = room["count_member"]
                    room_info["is_owner"] = True if chat_info[1] == email else False

                    charcater_sql = """
                    SELECT thumbnail_file_path
                    FROM `character`
                    WHERE active = True
                        AND character_id IN (SELECT member_id FROM `groupchat_member` WHERE is_user = False AND active = True AND groupchat_id = %s)
                        AND character_id NOT IN (
                            SELECT character_id
                            FROM `character_block`
                            WHERE email = %s
                        )
                        AND email NOT IN (
                                SELECT blocked_email
                                FROM `user_block`
                                WHERE email = %s
                        )
                    """
                    cursor.execute(charcater_sql, (room["chat_id"], email, email))
                    characters_info = cursor.fetchall()
                    if characters_info:
                        for character_info in characters_info:
                            room_info["ai_thumbnails"].append(
                                s3_asset_cf_domain
                                + "/"
                                + character_info["thumbnail_file_path"]
                            )

                    # groupchat chat 정보
                    latest_chat = groupchat_tb.query(
                        KeyConditionExpression=Key("groupchat_uuid").eq(room["chat_id"])
                        & Key("send_time").eq(room["last_send_time"])
                    )["Items"]
                    if latest_chat:
                        room_info["latest_chat"] = latest_chat[0]["msg"]
                        room_info["latest_chat_time"] = latest_chat[0]["send_time"]

                    chatroom_info_list.append(room_info)

    return {"data": chatroom_info_list}


def list_chatroom_v2(email: str, page_size: int, offset: int):
    query = f"""
    SELECT *
        FROM (
        SELECT
            chat.chat_id AS chatroom_uuid,
            IF(C.type = 'mystery', C.description, C.name) AS title,
            2 AS total_member,
            C.thumbnail_file_path AS ai_thumbnails,
            CMU.last_send_time,
            C.type,
            0 AS is_owner,
            CMU.notification AS notification_on
        FROM
            `chat` AS chat
        JOIN
            `chat_member` AS CMC
            ON CMC.chat_id = chat.chat_id AND CMC.is_user = 0 AND CMC.active = 1
        JOIN
            `chat_member` AS CMU
            ON CMU.chat_id = chat.chat_id AND CMU.is_user = 1 AND CMU.active = 1
        JOIN
            `character` AS C
            ON CMC.member_id = C.character_id
        LEFT JOIN
            `character_block` AS CB
            ON CMU.member_id = CB.email AND CMC.member_id = CB.character_id
        WHERE
            chat.active = 1
            AND CMU.member_id = '{email}'
            AND CB.email IS NULL

        UNION ALL

        SELECT
            G.groupchat_id AS chatroom_uuid,
            G.name,
            COUNT(DISTINCT GMC.member_id) + COUNT(DISTINCT GMU.member_id) AS total_member,
            GROUP_CONCAT(C.thumbnail_file_path) AS ai_thumbnails,
            GME.last_send_time,
            'group' AS type,
            IF(G.email = '{email}', 1, 0) AS is_owner,
            GME.notification AS notification_on
        FROM
            `groupchat` AS G
        JOIN
            `groupchat_member` AS GMC
            ON G.groupchat_id = GMC.groupchat_id AND GMC.is_user = 0 AND GMC.active = 1
        JOIN
            `groupchat_member` AS GMU
            ON G.groupchat_id = GMU.groupchat_id AND GMU.is_user = 1 AND GMU.active = 1
        JOIN
            `groupchat_member` AS GME
            ON G.groupchat_id = GME.groupchat_id AND GME.is_user = 1 AND GME.active = 1 AND GME.member_id = '{email}'
        JOIN
            `character` AS C
            ON GMC.member_id = C.character_id
        LEFT JOIN
            `character_block` AS CB
            ON GME.member_id = CB.email AND GMC.member_id = CB.character_id
        LEFT JOIN
            `user_block` AS UB
            ON GME.member_id = UB.email AND GMU.member_id = UB.blocked_email
        WHERE
            G.active = 1
            AND CB.email IS NULL
            AND UB.email IS NULL
        GROUP BY G.groupchat_id
    ) AS combined_chats
    ORDER BY last_send_time DESC
    LIMIT {page_size} OFFSET {offset}
    """
    chatroom_list = []
    db_connection = get_db_connection()
    with db_connection.cursor() as cursor:
        cursor.execute(query)
        chatroom_list = cursor.fetchall()
        for room in chatroom_list:
            latest_chat = ""
            latest_chat_time = ""
            room["is_owner"] = True if room["is_owner"] else False
            room["ai_thumbnails"] = room["ai_thumbnails"].split(",")
            room["ai_thumbnails"] = ["/" + s for s in room["ai_thumbnails"]]

            # latest chat
            if room["type"] == "group":
                groupchat_tb = dynamodb.get_resource_obj("idolmaster_groupchat")
                latest_chat_db = groupchat_tb.query(
                    KeyConditionExpression=Key("groupchat_uuid").eq(
                        room["chatroom_uuid"]
                    ),
                    ScanIndexForward=False,  # 내림차순 정렬
                    Limit=1,  # 가장 최근 메시지 1개만 가져오기
                )["Items"]
                if latest_chat_db:
                    latest_chat = latest_chat_db[0]["msg"]
                    latest_chat_time = latest_chat_db[0]["send_time"]
            else:
                chat_tb = dynamodb.get_resource_obj("idolmaster_chat")
                latest_chat_db = chat_tb.query(
                    KeyConditionExpression=Key("chatroom_uuid").eq(
                        room["chatroom_uuid"]
                    ),
                    ScanIndexForward=False,
                    Limit=1,
                )["Items"]
                if latest_chat_db:
                    latest_chat = latest_chat_db[0]["msg"]
                    latest_chat_time = latest_chat_db[0]["send_time"]

            if latest_chat_time:
                if isinstance(latest_chat_time, (int, float)) or (
                    isinstance(latest_chat_time, str)
                    and latest_chat_time.replace(".", "", 1).isdigit()
                ):
                    # 유닉스 타임스탬프 형식인 경우만 변환
                    dt = datetime.fromtimestamp(
                        float(latest_chat_time), tz=timezone.utc
                    )
                    latest_chat_time = dt.isoformat(timespec="microseconds")
                    if latest_chat_time.endswith("+00:00"):
                        latest_chat_time = latest_chat_time.replace("+00:00", "Z")
                elif isinstance(latest_chat_time, str) and "T" in latest_chat_time:
                    # 이미 ISO 형식인 경우 그대로 사용
                    pass

            room["latest_chat"] = latest_chat
            room["latest_chat_time"] = latest_chat_time
            del room["last_send_time"]
    return chatroom_list


@preprocessing_cursor
def list_member_ids(
    character_ids: list = [], emails: list = [], cursor: object = None
) -> list:
    """chatroom_member 테이블에 등록된 member_id 조회

    :param character_ids: 캐릭터 아이디 리스트
    :param emails: 사용자 email 리스트
    :param cursor: pymysql.connect().cursor()

    :return: chatroom_member 조회된 모든 데이터
    """

    # 조회 제약 조건
    if not character_ids and not emails:
        raise Exception("[ERROR] : chat.list_member_ids")

    member_ids = []
    character_ids_query = (
        f"character_id IN {tuple(character_ids)}" if character_ids else ""
    )
    emails_query = f"email IN {tuple(emails)}" if emails else ""
    where_query = (
        "OR".join([character_ids_query, emails_query])
        if character_ids and emails
        else character_ids_query + emails_query
    )
    query = f"SELECT * FROM `chatroom_member` WHERE {where_query}"
    cursor.execute(query)
    member_ids = cursor.fetchall()
    return member_ids


def set_evaluate_chat(email: str, chatroom_id: str, send_time: str, like: bool):
    db_connection = get_db_connection()
    with db_connection.cursor() as cursor:
        cursor.execute(
            "SELECT * FROM `chat_message_evaluate` WHERE chat_id = %s AND message_send_time = %s AND email = %s",
            (chatroom_id, send_time, email),
        )
        chat_evaluation = cursor.fetchone()

        if chat_evaluation:
            cursor.execute(
                "UPDATE `chat_message_evaluate` SET like_value = %s WHERE chat_id = %s AND message_send_time = %s AND email = %s",
                (like, chatroom_id, send_time, email),
            )
        else:
            cursor.execute(
                "INSERT INTO `chat_message_evaluate` (chat_id, message_send_time, email, like_value) VALUES (%s, %s, %s, %s)",
                (chatroom_id, send_time, email, like),
            )

    db_connection.commit()
    db_connection.close()


def set_notification(email: str, chatroom_id: str, notification: bool):
    db_connection = get_db_connection()
    with db_connection.cursor() as cursor:
        sql = "UPDATE `chat_member` SET notification = %s WHERE chat_id = %s AND member_id = %s AND active = TRUE"
        cursor.execute(sql, (notification, chatroom_id, email))
    db_connection.commit()
    db_connection.close()


def send_report(email: str, chatroom_id: str, subject: str, content: str):
    history_input = {
        "date": time.now().isoformat() + "Z",
        "chatroom_id": chatroom_id,
        "email": email,
        "subject": subject,
        "content": content,
        "solved": False,
    }

    # dynamoDB 저장
    table_name = "idolmaster_history_chatroom_report"
    report_history_tb = dynamodb.get_resource_obj(table_name)
    report_history_tb.put_item(Item=history_input)


def set_safe_chat(chatroom_id: str, value: bool):
    db_connection = get_db_connection()
    with db_connection.cursor() as cursor:
        sql = "UPDATE `chat` SET `safe_chat` = %s WHERE `chat_id` = %s"
        cursor.execute(sql, (value, chatroom_id))
    db_connection.commit()
    db_connection.close()


def update_mystery_chat_step(email: str, chatroom_id: str, current_step: str):
    db_connection = get_db_connection()
    with db_connection.cursor() as cursor:
        sql = "UPDATE `guessing_game_step` SET `current_step` = %s WHERE `chat_id` = %s"
        cursor.execute(sql, (current_step, chatroom_id))
    db_connection.commit()
    db_connection.close()
