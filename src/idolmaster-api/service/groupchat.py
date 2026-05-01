from decimal import Decimal
import os
import json
import traceback
from boto3.dynamodb.conditions import Key

import shortuuid

import const
from lib import time
from lib import client
from lib.decorator import preprocessing_cursor
from service import avatar as avatar_module
from thirdparty import dynamodb
from thirdparty.mariadb import get_db_connection


@preprocessing_cursor
def check_active(groupchat_id: str, cursor: object = None) -> bool:
    """그룹채팅방의 활성화 상태를 확인

    :param groupchat_id: 채팅방 id
    :param cursor: pymysql.connect().cursor()

    :return
        True: 현재 채팅방 활성화
        False: 현재 채팅방 비활성화 or 존재하지 않음
    """
    query = f"SELECT * FROM `groupchat` WHERE groupchat_id = '{groupchat_id}' AND active = 1"
    cursor.execute(query)
    return True if cursor.fetchone() else False


def check_member(email: str, chatroom_id: str):
    data = {}
    s3_asset_cf_domain = ""
    db_connection = get_db_connection()
    with db_connection.cursor() as cursor:
        sql = """
        SELECT G.accessibility, G.name,
            (SELECT COUNT(*) FROM `groupchat_member` AS GM WHERE G.groupchat_id = GM.groupchat_id AND GM.member_id = %s AND GM.active = TRUE) AS is_member,
            GROUP_CONCAT(C.thumbnail_file_path) AS thumbnail_files
        FROM `groupchat` AS G
            LEFT JOIN `groupchat_member` AS GM ON G.groupchat_id = GM.groupchat_id AND GM.active = TRUE
            LEFT JOIN `character` AS C ON GM.member_id = C.character_id AND C.active = TRUE
        WHERE G.groupchat_id = %s
        GROUP BY G.accessibility, G.name
        """
        cursor.execute(sql, (email, chatroom_id))
        result = cursor.fetchone()
        if result:
            data["accessibility"] = result["accessibility"]
            data["is_member"] = bool(result["is_member"])
            if result["accessibility"] == "private" and result["is_member"] == 0:
                data["ai_thumbnails"] = []
                data["title"] = result["name"]
                for thumbnail in result["thumbnail_files"].split(","):
                    data["ai_thumbnails"].append(s3_asset_cf_domain + "/" + thumbnail)

    return data


def create_chatroom(
    email: str,
    character_ids: list,
    name: str,
    description: str,
    accessibility: str,
    password: str,
    max_participants_num: int,
    language: str,
):
    # groupchat 정보
    uuid = shortuuid.ShortUUID().random(length=20)
    timestamp_at = str(round(Decimal(time.timestampnow()), 5))
    db_connection = get_db_connection()
    with db_connection.cursor() as cursor:
        # groupchat table put item
        groupchat_sql = "INSERT INTO `groupchat` (`groupchat_id`, `name`, `description`, `active`, `language`, `accessibility`, `password`, `max_participants_num`, `email`) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"
        cursor.execute(
            groupchat_sql,
            (
                uuid,
                name,
                description,
                True,
                language,
                accessibility,
                password,
                max_participants_num,
                email,
            ),
        )

        groupchat_user_sql = "INSERT INTO `groupchat_member` (`groupchat_id`, `member_id`, `active`, `notification`, `last_send_time`, `is_user`) VALUES (%s, %s, %s, %s, %s, %s)"
        cursor.execute(
            groupchat_user_sql, (uuid, email, True, True, timestamp_at, True)
        )

        for character_id in character_ids:
            groupchat_char_sql = "INSERT INTO `groupchat_member` (`groupchat_id`, `member_id`, `active`, `notification`, `last_send_time`, `is_user`) VALUES (%s, %s, %s, %s, %s, %s)"
            cursor.execute(
                groupchat_char_sql,
                (uuid, character_id, True, False, timestamp_at, False),
            )

    db_connection.commit()
    db_connection.close()

    return uuid


def enter_groupchat(
    email: str, chatroom_id: str, accessibility: str, input_password: str
):
    # 상태 코드
    # 0 : 입장 성공
    # 1 : 채팅방 없음
    # 2 : 채팅방 비활성화
    # 3 : 현재 인원수 최대치 이상
    # 4 : 비밀번호 틀림
    status_code = 0

    db_connection = get_db_connection()
    with db_connection.cursor() as cursor:
        # 현재 유저 수 조회
        sql = """
        SELECT COUNT(*) AS member_count, G.max_participants_num, G.active, G.password
        FROM `groupchat_member` AS GM
            JOIN `groupchat` AS G ON GM.groupchat_id = G.groupchat_id
        WHERE
            GM.groupchat_id = %s AND GM.is_user = TRUE AND GM.active = TRUE
        GROUP BY
            G.max_participants_num, G.active, G.password
        """
        cursor.execute(sql, (chatroom_id,))
        result = cursor.fetchone()

        if not result:
            status_code = 1
        if result["active"] is False:
            status_code = 2
        if result["member_count"] >= result["max_participants_num"]:
            status_code = 3

        # private일 경우 비밀번호 체크
        if accessibility == "private":
            if result["password"] != input_password or not input_password:
                status_code = 4

        # 입장 가능
        if not status_code:
            # groupchat user 정보 삽입
            timestamp_at = str(round(Decimal(time.timestampnow()), 5))
            groupchat_user_sql = """
            INSERT INTO `groupchat_member` (`groupchat_id`, `member_id`, `active`, `notification`, `last_send_time`, `is_user`)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE `active` = TRUE
            """
            cursor.execute(
                groupchat_user_sql, (chatroom_id, email, True, True, timestamp_at, True)
            )

            # 사용자 입장 알리기 - 소켓
            socket_data = {"type": "enter", "email": email}

            sql = """
            SELECT GC.connection_id, U.nickname, G.email
            FROM `groupchat_connection` AS GC, `user` AS U, `groupchat` AS G
            WHERE GC.email IN (
                SELECT GM.member_id
                FROM `groupchat_member` AS GM
                WHERE GM.groupchat_id = %s
                    AND GM.is_user = TRUE
                    AND GM.active = TRUE
            ) AND GC.groupchat_id = %s AND U.email = %s AND G.groupchat_id = GC.groupchat_id
            """
            cursor.execute(sql, (chatroom_id, chatroom_id, email))
            results = cursor.fetchall()
            if results:
                socket_data["nickname"] = results[0]["nickname"]

            # 입장 내역 저장
            if results[0]["email"] != email:
                groupchat_input = {
                    "groupchat_uuid": chatroom_id,
                    "send_time": timestamp_at,
                    "id": "system_message",
                    "msg": results[0]["nickname"] + " joined this group",
                }
                dynamodb.put_item("idolmaster_groupchat", groupchat_input)

    db_connection.commit()
    db_connection.close()

    return status_code


@preprocessing_cursor
def list_members(groupchat_id: str, cursor: object = None) -> list:
    """그룹채팅 맴버 조회

    :param groupchat_id: 그룹채팅방 id
    :param cursor: pymysql.connect().cursor()

    :return: 멤버 id 리스트 (캐릭터 id or email)
        [
            '{member_id}', ...
        ]
    """
    query = f"""
    SELECT
        GCM.member_id
    FROM `groupchat` AS GC
    JOIN
        `groupchat_member` AS GCM
        ON GC.groupchat_id = GCM.groupchat_id
    WHERE
        GC.groupchat_id = '{groupchat_id}'
        AND GC.active = 1
        AND GCM.active = 1
    """
    cursor.execute(query)
    return [item["member_id"] for item in cursor.fetchall()]


def get_chatroom_info(email: str, chatroom_id: str):
    data = {
        "room_type": "group",
        "title": "",
        "language": "",
        "members": [],
        "avatarInfo": [],
        "notification_on": None,
        "participants_num": None,
        "accessibility": None,
        "is_owner": None,
    }
    s3_asset_cf_domain = ""

    # 채팅방 정보 가져오기 =======================================
    db_connection = get_db_connection()
    with db_connection.cursor() as cursor:
        sql = """
        SELECT A.accessibility, A.name, A.email as owner_id, A.language, B.member_id, B.is_user,
            (SELECT COUNT(*) FROM `groupchat_member` AS GM WHERE GM.groupchat_id = B.groupchat_id AND GM.active = True AND GM.member_id = %s) AS is_member,
            (SELECT COUNT(*) FROM `groupchat_member` AS GM WHERE GM.groupchat_id = B.groupchat_id AND GM.active = True AND GM.is_user = TRUE) AS count_member,
            (SELECT notification FROM `groupchat_member` AS GM WHERE GM.groupchat_id = B.groupchat_id AND GM.member_id = %s) AS notification,
            (SELECT COUNT(*) FROM `groupchat_block` AS GB WHERE GB.groupchat_id = B.groupchat_id AND GB.blocked_email = B.member_id AND GB.`email` = %s) AS is_blocked,
            (SELECT build_file_path FROM `3dviewer_background` AS VB WHERE persons = 2 order by rand() LIMIT 1) AS build_url,
            (SELECT pose FROM `3dviewer_background` AS VB WHERE persons = 2 order by rand() LIMIT 1) AS pose
        FROM `groupchat` AS A, `groupchat_member` AS B
        WHERE B.groupchat_id = %s AND A.groupchat_id = B.groupchat_id AND B.active = TRUE
        """
        cursor.execute(sql, (email, email, email, chatroom_id))
        results = cursor.fetchall()

        if results:
            data["title"] = results[0]["name"]
            data["accessibility"] = results[0]["accessibility"]
            data["language"] = results[0]["language"]
            data["is_owner"] = True if results[0]["owner_id"] == email else False
            data["participants_num"] = results[0]["count_member"]
            data["notification_on"] = results[0]["notification"]
            # build_url = results[0]["build_url"]
            # build_files = {
            #     "Build.data.gz": build_url + "Build.data.gz",
            #     "Build.framework.js.gz": build_url + "Build.framework.js.gz",
            #     "Build.loader.js": build_url + "Build.loader.js",
            #     "Build.wasm.gz": build_url + "Build.wasm.gz"
            # }
            # data["build_url"] = build_files

            for idx, member in enumerate(results):
                # 유저
                if member["is_user"]:
                    members_map = {}
                    sql = "SELECT nickname FROM `user` WHERE `email` = %s"
                    cursor.execute(sql, (member["member_id"],))
                    result = cursor.fetchone()
                    members_map["name"] = result["nickname"]
                    members_map["id"] = member["member_id"]
                    members_map["is_blocked"] = True if member["is_blocked"] else False
                    data["members"].append(members_map)
                # 캐릭터
                else:
                    sql = """
                    SELECT C.thumbnail_file_path, C.name, A.avatar_file_path, A.gender
                    FROM `character` as C, `avatar` as A
                    WHERE C.character_id = %s
                        AND A.avatar_id = C.avatar_id
                        AND C.active = TRUE
                        AND C.character_id NOT IN (
                            SELECT character_id
                            FROM `character_block`
                            WHERE email = %s
                        )
                        AND C.email NOT IN (
                                SELECT blocked_email
                                FROM `user_block`
                                WHERE email = %s
                        )
                    """
                    cursor.execute(sql, (member["member_id"], email, email))
                    result = cursor.fetchone()
                    if result:
                        members_map = {}
                        members_map["id"] = member["member_id"]
                        members_map["is_blocked"] = (
                            True if member["is_blocked"] else False
                        )
                        members_map["name"] = result["name"]
                        members_map["thumbnail_url"] = (
                            s3_asset_cf_domain + "/" + result["thumbnail_file_path"]
                        )

                        avatarInfo_map = {}

                        avatarInfo_map["url"] = (
                            s3_asset_cf_domain + "/" + result["avatar_file_path"]
                        )
                        avatarInfo_map["id"] = member["member_id"]
                        avatarInfo_map["gender"] = result["gender"]
                        avatarInfo_map["idle_motion_path"] = (
                            "/"
                            + avatar_module.get_emotion_retargeting(
                                "Idle", result["avatar_file_path"], result["gender"]
                            )
                        )
                        # pose_length = len(results[0]["pose"].split(','))
                        # random_pose_idx = random.randint(0, pose_length - 1)
                        # avatarInfo_map["pose"] = results[0]["pose"].split(',')[random_pose_idx]

                        data["avatarInfo"].append(avatarInfo_map)
                        data["members"].append(members_map)

                background_info = [
                    {"id": "character", "url": "/background/normal/.jpg"}
                ]
                data["background_url"] = background_info

    # 3D background
    # response = s3.list_objects_v2(Bucket="idolmaster-asset", Prefix="background/")
    # files = [obj["Key"] for obj in response.get("Contents", [])]
    # if not files:
    #     return None
    # selected_file = random.choice(files)
    # background_file_url = gets3file(selected_file, 3600, False)
    # data["background_url"] = background_file_url

    return data


def get_previous_chat(email: str, groupchat_id: str, last_evaluated_key: dict):
    table_name = "idolmaster_groupchat"
    groupchat_table = dynamodb.get_resource_obj(table_name)

    def fetch_chats(groupchat_id, last_evaluated_key=None, limit=50):
        if last_evaluated_key:
            response = groupchat_table.query(
                KeyConditionExpression=Key("groupchat_uuid").eq(groupchat_id),
                Limit=limit,
                ScanIndexForward=False,
                ExclusiveStartKey=last_evaluated_key,
            )
        else:
            response = groupchat_table.query(
                KeyConditionExpression=Key("groupchat_uuid").eq(groupchat_id),
                Limit=limit,
                ScanIndexForward=False,
            )

        items = response["Items"]
        last_evaluated_key = response.get("LastEvaluatedKey")

        return items, last_evaluated_key

    previous_chat = []

    # 두 번째 호출부터: 다음 50개 항목 가져오기
    if last_evaluated_key:
        more_chats, last_evaluated_key = fetch_chats(groupchat_id, last_evaluated_key)
        previous_chat.extend(more_chats)
    # 첫 번째 호출: 첫 50개 항목 가져오기
    else:
        chats, last_evaluated_key = fetch_chats(groupchat_id, last_evaluated_key)
        previous_chat = chats

    # 내림차순으로 정렬
    previous_chat.sort(key=lambda x: x["send_time"])

    db_connection = get_db_connection()
    with db_connection.cursor() as cursor:
        # 내가 차단한 사용자 및 캐릭터 id 조회
        sql = f"""
        SELECT blocked_email AS id
        FROM `groupchat_block`
        WHERE groupchat_id = %s AND email = "{email}"

        UNION

        SELECT character_id AS id
        FROM `character_block`
        WHERE email = "{email}"

        UNION

        SELECT C.character_id AS id
        FROM `character` AS C
        JOIN `user_block` AS UB ON C.email = UB.blocked_email
        WHERE UB.email = "{email}"
        """
        cursor.execute(sql, (groupchat_id))
        results = cursor.fetchall()

        blocked_ids = set()
        for result in results:
            blocked_ids.add(result["id"])
        print(f"blocked_ids: {blocked_ids}")

        filtered_chat = [
            message for message in previous_chat if message["id"] not in blocked_ids
        ]

        # 만약 채팅이 없을 경우 캐릭터의 첫 메세지 추가
        if len(filtered_chat) == 0:
            sql = """
            SELECT A.member_id, CP.first_message, B.name, (SELECT nickname FROM `user` WHERE email = %s ) AS nickname
            FROM `groupchat_member` AS A, `character` AS B, `character_persona` AS CP
            WHERE A.`groupchat_id`= %s AND A.member_id = B.character_id AND B.character_id = CP.character_id
            """
            cursor.execute(sql, (email, groupchat_id))
            results = cursor.fetchall()

            for result in results:
                timestamp_at = str(round(Decimal(time.timestampnow()), 5))

                chat = {
                    "groupchat_uuid": groupchat_id,
                    "id": result["member_id"],
                    "msg": result["first_message"]
                    .replace("{{user}}", result["nickname"])
                    .replace("{{character}}", result["name"]),
                    "send_time": timestamp_at,
                }
                dynamodb.put_item(table_name, chat)
                filtered_chat.append(chat)

    return {"chats": filtered_chat, "last_evaluated_key": last_evaluated_key}


def leave_chatroom(email: str, chatroom_id: str):
    db_connection = get_db_connection()
    with db_connection.cursor() as cursor:
        sql = "UPDATE `groupchat_member` SET `active` = FALSE WHERE `groupchat_id` = %s AND member_id = %s"
        cursor.execute(sql, (chatroom_id, email))
    db_connection.commit()

    db_connection = get_db_connection()
    with db_connection.cursor() as cursor:
        sql = """
        SELECT `email`,
            (SELECT COUNT(*) FROM `groupchat_member` AS GM WHERE GM.groupchat_id = G.groupchat_id AND GM.active = TRUE AND GM.is_user = TRUE) AS remain_member_count
        FROM `groupchat` AS G
        WHERE `groupchat_id` = %s"""
        cursor.execute(sql, (chatroom_id))
        result = cursor.fetchone()
        # 방에 남은 유저가 0명
        if result["remain_member_count"] == 0:
            # groupchat active update
            sql = "UPDATE `groupchat` SET `active` = FALSE WHERE `groupchat_id` = %s"
            cursor.execute(sql, (chatroom_id))
            sql = "UPDATE `groupchat_member` SET `active` = FALSE WHERE groupchat_id = %s AND is_user = FALSE"
            cursor.execute(sql, (chatroom_id))

        # 방장 퇴장 시 챗방 비활성화 처리
        if result["email"] == email:
            sql = "UPDATE `groupchat` SET `active` = FALSE WHERE `groupchat_id` = %s"
            cursor.execute(sql, (chatroom_id))
            sql = (
                "UPDATE `groupchat_member` SET `active` = FALSE WHERE groupchat_id = %s"
            )
            cursor.execute(sql, (chatroom_id))

        # 사용자 퇴장 알리기
        socket_data = {"type": "leave", "email": email}
        sql = """
        SELECT GC.connection_id, U.nickname
        FROM `groupchat_connection` AS GC, `user` AS U
        WHERE GC.email IN (
            SELECT GM.member_id
            FROM `groupchat_member` AS GM
            WHERE GM.groupchat_id = %s
                AND GM.is_user = TRUE
                AND GM.active = TRUE
        ) AND GC.groupchat_id = %s AND U.email = %s
        """
        cursor.execute(sql, (chatroom_id, chatroom_id, email))
        results = cursor.fetchall()
        if results:
            socket_data["nickname"] = results[0]["nickname"]

            apigatewaymanagementapi = client.apigatewaymanagementapi_client(
                const.APIGATEWAY_MANAGEMENT_API_URL[os.environ["AWS_REGION"]][
                    os.environ["API_ALIAS"]
                ]
            )

            for result in results:
                try:
                    apigatewaymanagementapi.post_to_connection(
                        ConnectionId=result["connection_id"],
                        Data=json.dumps(socket_data),
                    )
                except apigatewaymanagementapi.exceptions.GoneException:
                    print("Connection is gone. Removing from database.")
                except Exception:
                    print(
                        " ====== ‼️ leaveChatroom ERROR: {} ======".format(
                            traceback.format_exc()
                        )
                    )

            # 퇴장 내역 저장
            timestamp_at = str(round(Decimal(time.timestampnow()), 5))
            groupchat_input = {
                "groupchat_uuid": chatroom_id,
                "send_time": timestamp_at,
                "id": "system_message",
                "msg": results[0]["nickname"] + " left this group",
            }
            dynamodb.put_item("idolmaster_groupchat", groupchat_input)

    db_connection.commit()
    db_connection.close()

    return {"chatroom_id": chatroom_id}


def list_groupchat(
    email: str,
    page_size: int,
    room_accessibility: str,
    search_keyword: str,
    offset: int,
):
    base_query = f"""
    SELECT A.groupchat_id, A.name, A.description, A.max_participants_num, A.language, A.accessibility, A.created_time,
        (
            SELECT COUNT(*)
            FROM `groupchat_member` AS B
            WHERE B.groupchat_id = A.groupchat_id
            AND B.active = TRUE
            AND B.member_id NOT IN (
                SELECT character_id
                FROM `character_block`
                WHERE email = "{email}"
            )
            AND B.member_id NOT IN (
                SELECT C.character_id
                FROM `character` AS C
                JOIN `user_block` AS CRB ON C.email = CRB.blocked_email
                WHERE CRB.email = "{email}"
            )
        ) AS count_member,
        GROUP_CONCAT(C.thumbnail_file_path) AS thumbnail_files

    FROM `groupchat` AS A
        JOIN `groupchat_member` AS GM ON A.groupchat_id = GM.groupchat_id AND GM.active = TRUE
        LEFT JOIN `character` AS C
            ON GM.member_id = C.character_id
            AND C.active = TRUE

    WHERE A.active = TRUE
        AND C.active = TRUE
        AND C.character_id NOT IN (
            SELECT character_id
            FROM `character_block`
            WHERE email = "{email}"
        )
        AND C.email NOT IN (
            SELECT blocked_email
            FROM `user_block`
            WHERE email = "{email}"
        )
    """
    conditions = []
    params = []
    s3_asset_cf_domain = ""

    # 방 타입에 따른 필터링
    if room_accessibility in ["public", "private"]:
        conditions.append("accessibility = %s")
        params.append(room_accessibility)

    # 검색어가 있을 경우
    if search_keyword:
        conditions.append(
            """
        (
            LOWER(A.name) LIKE LOWER(%s)
            OR LOWER(A.description) LIKE LOWER(%s)
        )
        """
        )
        params.extend([f"%{search_keyword}%", f"%{search_keyword}%"])

    # 최근 한달동안 채팅한 방만 조회
    else:
        conditions.append(
            "GM.last_send_time >= UNIX_TIMESTAMP(NOW() - INTERVAL 1 MONTH)"
        )

    # 조건 결합
    if conditions:
        base_query += " AND " + " AND ".join(conditions)

    final_query = f"""
        {base_query}
        GROUP BY A.groupchat_id, A.name, A.description, A.max_participants_num, A.language, A.accessibility, A.created_time
    """

    # 최신 순 정렬 추가
    final_query += """
        ORDER BY A.created_time DESC
    """

    query_with_pagenation = f"""
        {final_query}
        LIMIT {page_size} OFFSET {offset}
    """

    groupchat_list = []  # 리스트 정보
    list_total = 0  # 리스트 갯수
    db_connection = get_db_connection()
    with db_connection.cursor() as cursor:
        cursor.execute(query_with_pagenation, params)
        results = cursor.fetchall()

        for result in results:
            character_data = []

            character_thumbnails = result["thumbnail_files"].split(",")

            for thumbnail in character_thumbnails:
                character_map = {}
                character_map["id"] = shortuuid.ShortUUID().random(length=20)
                character_map["thumbnail_url"] = s3_asset_cf_domain + "/" + thumbnail
                character_data.append(character_map)

            groupchat_data = {
                "id": result["groupchat_id"],
                "name": result["name"],
                "description": result["description"],
                "participants_num": result["count_member"],
                "max_participants_num": str(
                    result["max_participants_num"] + len(character_thumbnails)
                ),
                "language": result["language"],
                "room_type": result["accessibility"],
                "characters": character_data,
            }

            groupchat_list.append(groupchat_data)

        cursor.execute(final_query, params)
        results = cursor.fetchall()
        list_total = len(results)

    return {"chats": groupchat_list, "total_count": list_total}


def set_notification(email: str, groupchat_id: str, notification: bool):
    db_connection = get_db_connection()
    with db_connection.cursor() as cursor:
        sql = "UPDATE `groupchat_member` SET notification = %s WHERE groupchat_id = %s AND member_id = %s AND active = TRUE"
        cursor.execute(sql, (notification, groupchat_id, email))
    db_connection.commit()
    db_connection.close()


def update_block_user(
    email: str, groupchat_id: str, block_user_id: str, set_value: bool
):
    db_connection = get_db_connection()
    with db_connection.cursor() as cursor:
        select_sql = "SELECT COUNT(*) FROM `groupchat_block` WHERE email = %s AND groupchat_id = %s AND blocked_email = %s"
        cursor.execute(select_sql, (email, groupchat_id, block_user_id))
        result = cursor.fetchone()["COUNT(*)"]

        # 사용자 차단
        if set_value and result < 1:
            sql = "INSERT INTO `groupchat_block` (groupchat_id, email, blocked_email) VALUES (%s, %s, %s)"
            cursor.execute(sql, (groupchat_id, email, block_user_id))

        # 차단 취소
        elif not set_value and result >= 1:
            sql = "DELETE FROM `groupchat_block` WHERE groupchat_id = %s AND email = %s AND blocked_email = %s"
            cursor.execute(sql, (groupchat_id, email, block_user_id))

    db_connection.commit()
    db_connection.close()
