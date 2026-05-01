import shortuuid

import const
from lib import time
from lib.decorator import preprocessing_cursor
from lib.parser import check_ban
from thirdparty import (cognito, dynamodb, firebase_admin)
from thirdparty.mariadb import get_db_connection


def block_and_report_creator(email: str, creator_email: str, report_message: str):
    ret = {}
    db_connection = get_db_connection()
    with db_connection.cursor() as cursor:
        sql = (
            "SELECT COUNT(*) FROM `user_block` WHERE email = %s AND blocked_email = %s"
        )
        cursor.execute(sql, (email, creator_email))
        result = cursor.fetchone()

        if result and result["COUNT(*)"] == 0:
            cursor.execute(
                "INSERT INTO `user_block` (email, blocked_email, message) VALUES (%s, %s, %s)",
                (email, creator_email, report_message),
            )
            ret["message"] = "Creator has been successfully blocked and reported."
        else:
            ret["message"] = "This creator has been already blocked and reported."

    db_connection.commit()
    db_connection.close()
    return ret


def check_nickname(nickname: str) -> dict:
    """닉네임 사용 가능한지 확인

    :param nickname: 닉네임

    :return
        {
            'possibility': bool,   # 닉네임 가능 여부
            'ban_list': list   # 닉네임에 포함되어 있는 금지어 리스트
        }
    """
    categories = [    # 필터링 적용 할 ban_word 파일명
        "service",
        "profanity",
        "racist",
        "sexual",
        "etc"
    ]
    return check_ban(nickname, categories=categories)


def check_premium(email: str) -> bool:
    """프리미엄 구독 확인"""
    res = False
    db_connection = get_db_connection()
    with db_connection as db:
        cursor = db.cursor()
        query = f"""
        SELECT email, premium
        FROM `user`
        WHERE email = '{email}'
        """
        cursor.execute(query)
        res = cursor.fetchone().get("premium")
        res = True if res else False
    return res


@preprocessing_cursor
def check_used_email(email: str, cursor: object = None):
    """email이 사용 중인지 확인

    :param email: 사용자 email
    :param cursor: pymysql.connect().cursor()

    :return
        True: email 사용 중
        False: email 사용 안함
    """
    cursor.execute(
        "SELECT COUNT(*) FROM `user` WHERE email = %s AND active = %s",
        (
            email,
            True,
        ),
    )
    result = cursor.fetchone()

    # TODO
    if result["COUNT(*)"]:
        res = True
    else:
        res = False

    return res


def check_used_name(name: str):
    db_connection = get_db_connection()
    with db_connection.cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) FROM `user` WHERE name = %s AND active = %s",
            (
                name,
                True,
            ),
        )
        result = cursor.fetchone()

        # TODO
        if result["COUNT(*)"] > 0:
            return True  # 해당 name이 사용 중이라면
        else:
            return False  # 사용 중이 아니라면


def delete_account(email: str, leave_memo: str):
    utc_now = time.now()
    utc_now_iso = utc_now.isoformat() + "Z"
    email_deactivated = shortuuid.uuid()
    db_connection = get_db_connection()
    with db_connection.cursor() as cursor:
        # 사용자 체크
        cursor.execute(
            "SELECT * FROM `user` WHERE email = %s AND active = TRUE", (email)
        )
        result = cursor.fetchone()
        user_id = result["id"]

        # 사용자 비활성화 처리 및 개인정보 삭제
        query = f"""
            UPDATE
                `user`
            SET
                active = False,
                email = '{email_deactivated}'
            WHERE
                email = '{email}'
        """
        cursor.execute(query)

        # 사용자가 생성한 캐릭터 삭제
        cursor.execute(
            """
            SELECT
                C.character_id,
                C.avatar_id
            FROM `character` AS C
            LEFT JOIN `content_chatroom_character` AS CCC ON C.character_id = CCC.character_id
            WHERE
                C.email = %s
                AND CCC.character_id IS NULL
            GROUP BY C.character_id
            """, (email_deactivated)
        )
        characters = cursor.fetchall()

        for character in characters:
            # 모든 채팅방에서 사용자가 만든 캐릭터 삭제
            # chatroom
            sql = "UPDATE `chat_member` SET `active` = FALSE WHERE `member_id` = %s"
            cursor.execute(sql, (character["character_id"]))
            # groupchat
            sql = "UPDATE `groupchat_member` SET `active` = FALSE WHERE `member_id` = %s"
            cursor.execute(sql, (character["character_id"]))

            # 컨텐츠에서 사용하지 않는 캐릭터 삭제
            sql = "UPDATE `character` SET active = %s WHERE character_id = %s"
            cursor.execute(sql, (False, character["character_id"]))

        # 사용자가 생성한 아바타 삭제 (컨텐츠에서 사용 X)
        content_avatar_ids = [character["avatar_id"] for character in characters]
        if content_avatar_ids:
            avatar_ids_str = "','".join(content_avatar_ids)
            sql = f"""
            UPDATE `avatar`
            SET active = 0
            WHERE
                email = '{email_deactivated}'
                and avatar_id NOT IN ('{avatar_ids_str}')
            """
            cursor.execute(sql)

        # copy한 타사용자의 아바타 삭제
        cursor.execute(
            "SELECT COUNT(*) FROM `character_copy` WHERE email = %s", (email)
        )
        result = cursor.fetchall()
        if result and result[0]["COUNT(*)"] > 0:
            sql = """DELETE FROM `character_copy` WHERE email = %s"""
            cursor.execute(sql, (email))

        # 좋아요 누른 캐릭터 삭제
        cursor.execute(
            "SELECT COUNT(*) FROM `character_like` WHERE email = %s", (email)
        )
        result = cursor.fetchall()
        if result and result[0]["COUNT(*)"] > 0:
            sql = """DELETE FROM `character_like` WHERE email = %s"""
            cursor.execute(sql, (email))

        # 컨텐츠 좋아요 삭제
        sql = """DELETE FROM `like` WHERE email = %s"""
        cursor.execute(sql, (email_deactivated))

        # block 삭제
        sql = """DELETE FROM `block` WHERE user_id = %s"""
        cursor.execute(sql, (user_id))

        # 채팅방 나가기
        # chatroom
        sql = "UPDATE `chat` SET `active` = FALSE WHERE `chat_id` IN (SELECT chat_id FROM `chat_member` WHERE member_id = %s)"
        cursor.execute(sql, (email))
        sql = "UPDATE `chat_member` SET `active` = FALSE, `member_id` = %s WHERE `member_id` = %s"
        cursor.execute(sql, (email_deactivated, email))
        # groupchat
        sql = "UPDATE `groupchat` SET `active` = FALSE WHERE `email` = %s"
        cursor.execute(sql, (email_deactivated))
        sql = "UPDATE `groupchat_member` SET `active` = FALSE, `member_id` = %s WHERE `member_id` = %s"
        cursor.execute(sql, (email_deactivated, email))

    db_connection.commit()
    db_connection.close()

    # 탈퇴 내역 저장
    table_name = "idolmaster_history_leave"
    history_input = {
        "date": utc_now_iso,
        "email": email,
        "leave_memo": leave_memo,
        "user_id": user_id,
        "email_deactivated": email_deactivated
    }
    dynamodb.put_item(table_name, history_input)


@preprocessing_cursor
def get_platform_v1(email: str, cursor: object = None) -> str:
    """사용자 계정의 IdP 조회.
    API v1 에서만 사용.
    """
    user_cognito = cognito.get_user_by_email(email)
    platform = const.IDENTITY_PROVIDER_COGNITO
    idp = user_cognito.get("provider_name")

    # IdP 확인
    if idp == "Google":
        platform = const.IDENTITY_PROVIDER_GOOGLE
    elif idp == "SignInWithApple":
        platform = const.IDENTITY_PROVIDER_APPLE
    elif idp == "Facebook":
        platform = const.IDENTITY_PROVIDER_FACEBOOK

    return platform


def get_user_info(email: str, fcm_token: str):
    data = {}
    db_connection = get_db_connection()
    with db_connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                id,
                email,
                name,
                nickname,
                language,
                gender,
                birth_date,
                privacy_agree,
                marketing_agree,
                premium
            FROM `user`
            WHERE
                email = %s
                AND active = %s
            """,
            (
                email,
                True,
            ),
        )
        result = cursor.fetchone()

        if result:
            birth = result.get("birth_date")
            data["id"] = result["id"]
            data["email"] = result["email"]
            data["name"] = result.get("name")
            data["nickname"] = result["nickname"]
            data["language"] = result.get("language")
            data["gender"] = result["gender"]
            data["birth_date"] = birth.isoformat() if birth else None
            data["privacy_agree"] = result["privacy_agree"]
            data["marketing_agree"] = result["marketing_agree"]
            data["premium"] = result["premium"]

            if fcm_token is not None:
                cursor.execute(
                    "UPDATE `user` SET fcm_token = %s WHERE email = %s AND active = %s",
                    (fcm_token, email, True),
                )
                db_connection.commit()

    return data


@preprocessing_cursor
def get_user_info_by_id(user_id: int, cursor: object = None):
    """사용자 계정 정보 조회"""
    cursor.execute(
        "SELECT * FROM `user` WHERE id = %s AND active = %s",
        (user_id, True),
    )
    return cursor.fetchone()


def list_favorite_character(email: str):
    data = []
    db_connection = get_db_connection()
    with db_connection:
        with db_connection.cursor() as cursor:
            sql = """SELECT character_id FROM `character_like` WHERE email = %s"""
            cursor.execute(sql, (email))
            result = cursor.fetchall()  # character_uuid를 담은 튜플 리스트 반환

            for row in result:
                character_uuid = row["character_id"]

                sql = """
                SELECT name, description, email, active, type,
                    CONCAT('/', thumbnail_file_path) AS thumbnail_file_path
                FROM `character`
                WHERE character_id = %s
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
                cursor.execute(sql, (character_uuid, email, email))
                character_info = cursor.fetchone()

                if character_info and character_info["active"]:

                    datamap = {}

                    datamap["character_id"] = character_uuid
                    datamap["character_name"] = character_info["name"]
                    datamap["character_desc"] = character_info["description"]
                    datamap["type"] = character_info["type"]
                    datamap["character_image"] = character_info["thumbnail_file_path"]

                    # 생성한 유저 이름 조회
                    cursor.execute(
                        "SELECT name FROM `user` WHERE email = %s",
                        (character_info["email"],),
                    )
                    user_result = cursor.fetchone()
                    if user_result:
                        create_username = user_result["name"]
                    else:
                        create_username = ""

                    datamap["create_username"] = create_username

                    # 좋아요 수
                    cursor.execute(
                        "SELECT COUNT(*) FROM `character_like` WHERE character_id = %s",
                        (character_uuid,),
                    )
                    result = cursor.fetchone()

                    datamap["liked_count"] = int(result["COUNT(*)"])

                    # 좋아요 여부
                    cursor.execute(
                        "SELECT COUNT(*) FROM `character_like` WHERE email = %s AND character_id = %s",
                        (
                            email,
                            character_uuid,
                        ),
                    )
                    result = cursor.fetchone()

                    is_liked = False

                    if result["COUNT(*)"] > 0:
                        is_liked = True

                    datamap["is_liked"] = is_liked

                    data.append(datamap)
    return {"data": data}


def list_creation_character(email: str):
    data = []
    db_connection = get_db_connection()
    with db_connection:
        with db_connection.cursor() as cursor:
            sql = """SELECT character_id, name, description, CONCAT('/', thumbnail_file_path) AS thumbnail_file_path, type FROM `character` WHERE email = %s AND active = %s AND type != 'mission' ORDER BY modified_time DESC"""
            cursor.execute(sql, (email, True))
            result = cursor.fetchall()

            for row in result:
                datamap = {}

                datamap["character_id"] = row["character_id"]
                datamap["character_name"] = row["name"]
                datamap["character_desc"] = row["description"]
                datamap["type"] = row["type"]
                datamap["character_image"] = row["thumbnail_file_path"]

                # 생성한 유저 이름 조회
                cursor.execute("SELECT name FROM `user` WHERE email = %s", (email,))
                user_result = cursor.fetchone()
                if user_result:
                    create_username = user_result["name"]
                else:
                    create_username = ""

                datamap["create_username"] = create_username

                # 좋아요 수
                cursor.execute(
                    "SELECT COUNT(*) FROM `character_like` WHERE character_id = %s",
                    (row["character_id"],),
                )
                result = cursor.fetchone()

                datamap["liked_count"] = int(result["COUNT(*)"])

                # 좋아요 여부
                cursor.execute(
                    "SELECT COUNT(*) FROM `character_like` WHERE email = %s AND character_id = %s",
                    (
                        email,
                        row["character_id"],
                    ),
                )
                result = cursor.fetchone()

                is_liked = False

                if result["COUNT(*)"] > 0:
                    is_liked = True

                datamap["is_liked"] = is_liked

                data.append(datamap)
    return {"data": data}


def save_login_history(email: str, user_ip: str):
    # mariaDB 저장
    current_time = time.now()
    connection = get_db_connection()
    with connection.cursor() as cursor:
        sql = "UPDATE `user` SET recent_login_date = %s WHERE email = %s"
        cursor.execute(sql, (current_time.strftime("%Y%m%d%H%M%S"), email))
    connection.commit()
    connection.close()

    history_input = {
        "date": current_time.isoformat() + "Z",
        "email": email,
        "ip": user_ip,
    }

    # dynamoDB 저장
    table_name = "idolmaster_history_login"
    dynamodb.put_item(table_name, history_input)


def save_user_info(
    email: str,
    platform: str,
    name: str,
    nickname: str,
    gender: str,
    birth_date: str,
    language: str,
    privacy_agree: bool,
    avatar_agree: bool,
    marketing_agree: bool,
) -> None:
    manager = False
    avaturn_user_id = None
    db_connection = get_db_connection()

    with db_connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM `user` WHERE email = %s", (email,))
        result = cursor.fetchone()

        # birth_date 기본값
        if not birth_date:
            birth_date = "9999-12-31"

        # 사용자가 이미 존재하는 경우 active를 True로 설정
        if result["COUNT(*)"] > 0:
            update_sql = """
            UPDATE `user`
            SET
                name = %s,
                nickname = %s,
                gender = %s,
                birth_date = %s,
                language = %s,
                privacy_agree = %s,
                marketing_agree = %s,
                avatar_agree = %s,
                active = %s,
                avaturn_user_id = %s,
                platform = %s
            WHERE email = %s
            """
            cursor.execute(
                update_sql,
                (
                    name,
                    nickname,
                    gender,
                    birth_date,
                    language,
                    privacy_agree,
                    marketing_agree,
                    avatar_agree,
                    True,
                    avaturn_user_id,
                    platform,
                    email,
                ),
            )
        # 사용자가 존재하지 않는 경우 insert
        else:
            insert_sql = """
            INSERT INTO `user` (
                `email`,
                `platform`,
                `name`,
                `nickname`,
                `gender`,
                `birth_date`,
                `language`,
                `manager`,
                `privacy_agree`,
                `marketing_agree`,
                `avatar_agree`,
                `active`,
                `avaturn_user_id`)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""
            cursor.execute(
                insert_sql,
                (
                    email,
                    platform,
                    name,
                    nickname,
                    gender,
                    birth_date,
                    language,
                    manager,
                    privacy_agree,
                    marketing_agree,
                    avatar_agree,
                    True,
                    avaturn_user_id,
                ),
            )

    db_connection.commit()
    db_connection.close()


def send_report(email: str, subject: str, explanation: str):
    history_input = {
        "date": time.now().isoformat() + "Z",
        "email": email,
        "subject": subject,
        "content": explanation,
        "solved": False,
    }

    # dynamoDB 저장
    table_name = "idolmaster_history_report"
    dynamodb.put_item(table_name, history_input)


def subscribe_premium(email: str) -> None:
    """프리미엄 구독 적용

    :param email: email
    """
    db_connection = get_db_connection()
    with db_connection as db:
        cursor = db.cursor()
        query = f"""
        UPDATE `user`
        SET premium = 1
        WHERE email = '{email}'
        """
        cursor.execute(query)
        db.commit()


def update_language(email, new_language):
    db_connection = get_db_connection()
    with db_connection.cursor() as cursor:
        sql = "UPDATE `user` SET language = %s WHERE email = %s"
        cursor.execute(sql, (new_language, email))
    db_connection.commit()
    db_connection.close()


def update_nickname(email, new_nickname):
    db_connection = get_db_connection()
    with db_connection.cursor() as cursor:
        sql = "UPDATE `user` SET nickname = %s WHERE email = %s"
        cursor.execute(sql, (new_nickname, email))
    db_connection.commit()
    db_connection.close()


@preprocessing_cursor
def update_user(
    email: str, language: str, nickname: str, cursor: object = None
) -> None:
    """사용자 계정 정보 수정

    :param email: 수정할 계정 email
    :param language: 사용 언어
    :param nickname: 사용자 별명
    :param cursor: pymysql.connect().cursor()
    """
    sql_set = []
    if language:
        sql_set.append(f"language = '{language}'")
    if nickname:
        sql_set.append(f"nickname = '{nickname}'")
    sql_set = ", ".join(sql_set)
    if sql_set:
        sql = f"UPDATE `user` SET {sql_set} WHERE email = '{email}'"
        cursor.execute(sql)


def unsubscribe_premium(email: str) -> None:
    """프리미엄 구독 취소

    :param email: email
    """
    db_connection = get_db_connection()
    with db_connection as db:
        cursor = db.cursor()
        query = f"""
        UPDATE `user`
        SET premium = 0
        WHERE email = '{email}'
        """
        cursor.execute(query)
        db.commit()


@preprocessing_cursor
def validate_fcm_token(fcm_token: str, user_id: int, cursor: object = None) -> bool:
    """FCM 토큰 유효성 검사

    :param fcm_token: FCM 토큰
    :param user_id: 사용자 ID
    :param cursor: pymysql.connect().cursor()

    :return: 유효한 경우 True, 유효하지 않은 경우 False
    """
    firebase_notification = firebase_admin.FirebaseNotification()
    valid = firebase_notification.validate_token(fcm_token)

    # 유효한 경우 fcm_token 업데이트
    if valid:
        cursor.execute(
            "UPDATE `user` SET fcm_token = %s WHERE id = %s",
            (fcm_token, user_id),
        )

    return valid
