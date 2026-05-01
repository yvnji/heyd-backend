import os
from datetime import datetime
from datetime import timedelta

import shortuuid
from botocore.signers import CloudFrontSigner

import const
from lib import time
from lib import client
from lib import crypto
from lib.decorator import preprocessing_cursor
from lib.exception import IdolmasterResourceNotFoundExeption
from service import avatar as avatar_module
from thirdparty import (avaturn,
                        dynamodb,
                        lambda_module,
                        s3)
from thirdparty.mariadb import get_db_connection


def block_and_report(email: str, character_id: str, report_message: str):
    blocked = False
    db_connection = get_db_connection()
    with db_connection.cursor() as cursor:
        sql = "SELECT COUNT(*) FROM `character_block` WHERE email = %s AND character_id = %s"
        cursor.execute(sql, (email, character_id))
        result = cursor.fetchone()

        if result and result["COUNT(*)"] == 0:
            cursor.execute(
                "INSERT INTO `character_block` (email, character_id, message) VALUES (%s, %s, %s)",
                (email, character_id, report_message),
            )

            # 1대1 채팅방 비활성화
            sql = """
            SELECT DISTINCT a.chat_id
            FROM `chat_member` a
            WHERE EXISTS (
                SELECT 1
                FROM `chat_member` b
                WHERE b.chat_id = a.chat_id
                    AND b.`member_id` = %s
            )
            AND EXISTS (
                SELECT 1
                FROM `chat_member` c
                WHERE c.chat_id = a.chat_id
                    AND c.`member_id` = %s
            )"""
            cursor.execute(sql, (email, character_id))
            chatroom_uuid = cursor.fetchone()

            if chatroom_uuid:
                cursor.execute(
                    "UPDATE `chat_member` SET active = FALSE WHERE chat_id = %s",
                    (chatroom_uuid["chat_id"]),
                )
                cursor.execute(
                    "UPDATE `chat` SET active = FALSE WHERE chat_id = %s",
                    (chatroom_uuid["chat_id"]),
                )
        else:
            blocked = True

    db_connection.commit()
    db_connection.close()
    return blocked


@preprocessing_cursor
def check_file_path(character_id: str, cursor: object = None) -> None:
    """캐릭터 정보에 있는 파일 패스들이 실제 존재하는지 확인.
    파일이 없을 경우 404 에러 발생.

    :param character_id: 캐릭터 id
    :param cursor: pymysql.connect().cursor()
    """
    # 캐릭터 썸네일 파일 확인
    query = f"""
    SELECT
        avatar_id,
        thumbnail_file_path
    FROM
        `character`
    WHERE
        character_id = '{character_id}'
    """
    cursor.execute(query)
    item = cursor.fetchone()

    if item["thumbnail_file_path"]:
        try:
            s3.check_object(
                const.S3_BUCKET_NAME[os.environ["AWS_REGION"]][os.environ["API_ALIAS"]],
                item["thumbnail_file_path"],
            )
        except IdolmasterResourceNotFoundExeption:
            raise IdolmasterResourceNotFoundExeption(
                message=f"File path not found (character id : {character_id})"
            )

    # 아바타 파일 확인
    avatar_module.check_file_path(item["avatar_id"], cursor=cursor)


def copy_avatar(email: str, character_id: str):
    db_connection = get_db_connection()
    with db_connection.cursor() as cursor:
        cursor.execute(
            "SELECT avatar_id FROM `character` WHERE character_id = %s AND active = TRUE",
            (character_id,),
        )
        character_result = cursor.fetchone()

        if character_result:
            avaturn_id = character_result["avatar_id"]
            cursor.execute(
                """
            SELECT COUNT(*) as is_copied,
            (
                SELECT COUNT(*)
                FROM `avatar`
                WHERE email = %s AND avatar_id = %s
            ) as is_mine
            FROM `character_copy`
            WHERE email = %s AND avatar_id = %s
            """,
                (email, avaturn_id, email, avaturn_id),
            )
            result = cursor.fetchone()
            if not result["is_copied"] and not result["is_mine"]:
                sql = """INSERT INTO `character_copy` (`email`, `avatar_id`) VALUES (%s, %s)"""
                cursor.execute(sql, (email, avaturn_id))
    db_connection.commit()
    db_connection.close()


def create_character(
    email: str,
    thumbnail_file_path: str,
    avaturn_character_id: str,
    name: str,
    first_message: str,  # opening
    description: str,  # tag_line
    basic_info: str,  # persona
    show_persona: int,  # 0 | 1
    generate_type: str,  # 'preset' | 'user' | 'avaturn'
    character_type: str,  # 'user'  | 'celeb'  | 'preset'  | 'mystery'  | 'concept'
    llm_type: str,
):
    llm_type = "llama3"
    certified = 0
    now_date = time.now()
    uuid = shortuuid.ShortUUID().random(length=20)
    db_connection = get_db_connection()
    with db_connection.cursor() as cursor:
        sql = """
        INSERT INTO `character` (character_id, email, thumbnail_file_path, name, active, certified, created_time, modified_time, description, avatar_id, show_persona, type)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        cursor.execute(
            sql,
            (
                uuid,
                email,
                thumbnail_file_path,
                name,
                True,
                certified,
                now_date,
                now_date,
                description,
                avaturn_character_id,
                show_persona,
                character_type,
            ),
        )

        # llm call, 추가 정보 가져옴

        sql = """
        INSERT INTO `character_persona` (character_id, basic_info, first_message, llm_type)
        VALUES (%s, %s, %s, %s)
        """
        cursor.execute(sql, (uuid, str(basic_info), first_message, llm_type))
    db_connection.commit()
    db_connection.close()

    response_data = {"generate_type": generate_type, "character_id": uuid}

    return response_data


def create_comment(email: str, character_id: str, content: str):
    db_connection = get_db_connection()
    with db_connection.cursor() as cursor:
        sql = """
            INSERT INTO `character_comment` (character_id, email, content, active)
            VALUES (%s, %s, %s, TRUE)
        """
        cursor.execute(sql, (character_id, email, content))

        # if cursor.rowcount > 0:
        #     returncode = 1

    db_connection.commit()
    db_connection.close()


@preprocessing_cursor
def delete_avatar(avaturn_id: str, cursor: object = None):
    # Avatar active False
    sql = """UPDATE `avatar` SET active = FALSE WHERE avatar_id = %s"""
    cursor.execute(sql, (avaturn_id))

    # copy한 아바타
    sql = """DELETE FROM `character_copy` WHERE avatar_id = %s"""
    cursor.execute(sql, (avaturn_id))

    # 캐릭터 처리
    cursor.execute(
        "SELECT character_id FROM `character` WHERE avatar_id = %s", (avaturn_id)
    )
    character_ids = [c["character_id"] for c in cursor.fetchall()]
    for character_id in character_ids:
        delete_character(character_id, cursor=cursor)


@preprocessing_cursor
def delete_character(character_id: str, cursor: object = None):
    # character active update
    cursor.execute(
        "UPDATE `character` SET active = %s WHERE character_id = %s",
        (False, character_id),
    )

    # 모든 채팅방에서 캐릭터 삭제
    # chatroom
    sql = "UPDATE `chat` SET `active` = FALSE WHERE `chat_id` IN (SELECT chat_id FROM `chat_member` WHERE member_id = %s)"
    cursor.execute(sql, (character_id))
    sql = "UPDATE `chat_member` SET `active` = FALSE WHERE `member_id` = %s"
    cursor.execute(sql, (character_id))
    # groupchat
    sql = "UPDATE `groupchat_member` SET `active` = FALSE WHERE `member_id` = %s"
    cursor.execute(sql, (character_id))
    # mission game chat
    sql = "UPDATE `chatroom_member` SET active = 0 WHERE character_id = %s"
    cursor.execute(sql, (character_id))
    sql = "DELETE FROM `mission_game_chat_character` WHERE character_id = %s"
    cursor.execute(sql, (character_id))


def delete_comment(email: str, comment_id: str, character_id: str):
    db_connection = get_db_connection()
    with db_connection.cursor() as cursor:
        # 댓글 수정
        sql = """
            UPDATE `character_comment`
            SET active = FALSE
            WHERE character_id = %s AND email = %s AND comment_id = %s
        """
        cursor.execute(sql, (character_id, email, comment_id))

    db_connection.commit()
    db_connection.close()


def delete_emoji(email: str, character_id: str, emoji_id: str):
    db_connection = get_db_connection()
    with db_connection.cursor() as cursor:
        # 기존 반응 체크
        cursor.execute(
            """SELECT COUNT(*) as reaction_exists FROM `emoji_reaction` WHERE character_id = %s AND email = %s AND emoji_id = %s""",
            (character_id, email, emoji_id),
        )
        existing_reaction = cursor.fetchone()

        if existing_reaction["reaction_exists"] > 0:
            # 리액션 삭제
            delete_query = """
                DELETE FROM `emoji_reaction`
                WHERE character_id = %s AND email = %s AND emoji_id = %s
            """
            cursor.execute(delete_query, (character_id, email, emoji_id))

    db_connection.commit()
    db_connection.close()


def edit_character(
    thumbnail_file_path: str,
    character_id: str,
    name: str,
    description: str,  # tag_line
    first_message: str,  # opening
    basic_info: str,  # persona
    show_persona: str,
    avatar_id: str = None
):
    # model_file_path = '' # s3 path ("preset_character/~.glb" 또는 "user_character/~.glb")
    llm_type = "llama3"
    now_date = time.now()
    thumbnail_file_path_query = ""

    # 썸네일 파일 수정
    if thumbnail_file_path:
        print(f"바꿀 파일명: {thumbnail_file_path}")
        thumbnail_file_path_query = f"thumbnail_file_path = '{thumbnail_file_path}'"

    db_connection = get_db_connection()
    with db_connection.cursor() as cursor:
        # `thumbnail_file_path`가 빈 문자열이 아니면 해당 필드 포함
        set_clause = [
            "name = %s",
            "description = %s",
            "active = TRUE",
            "modified_time = %s",
            "show_persona = %s",
            thumbnail_file_path_query,
        ]
        params = [
            name,
            description,
            now_date,
            show_persona,
            character_id,
        ]

        # avatar_id 확인
        if avatar_id:
            set_clause = ["avatar_id = %s"] + set_clause
            params = [avatar_id] + params

        # 필터링 후 쿼리 문자열
        set_clause = [clause for clause in set_clause if clause]  # 빈 항목 제거
        set_sql = ", ".join(set_clause)

        # 쿼리 실행
        sql = f"""
            UPDATE `character`
            SET {set_sql}
            WHERE character_id = %s
        """
        cursor.execute(sql, params)
        sql = """
            UPDATE `character_persona`
            SET
                basic_info = %s,
                first_message = %s,
                llm_type = %s
            WHERE character_id = %s
        """
        cursor.execute(sql, (str(basic_info), first_message, llm_type, character_id))
    db_connection.commit()
    db_connection.close()


def edit_comment(email: str, character_id: str, content: str, comment_id: str):
    db_connection = get_db_connection()
    with db_connection.cursor() as cursor:
        sql = """
            UPDATE `character_comment`
            SET content = %s
            WHERE character_id = %s AND email = %s AND comment_id = %s
        """
        cursor.execute(sql, (content, character_id, email, comment_id))

    db_connection.commit()
    db_connection.close()


@preprocessing_cursor
def get_avatar(avatar_id: str, email: str = None, cursor: object = None) -> dict:
    """아바타 정보 조회

    :param avatar_id: 아바타 id
    :param email: 사용자 email
    :param cursor: pymysql.connect().cursor()

    :return
        {
            avatar_id: str,
            created_time: str,
            modified_time: str,
            email: str,
            avatar_file_path: str,
            thumbnail_file_path: str,
            type: str,
            gender: str
        }
    """
    query_where_email = f"AND email = '{email}'" if email else ""
    query = f"""
    SELECT
        avatar_id,
        created_time,
        modified_time,
        email,
        avatar_file_path,
        thumbnail_file_path,
        type,
        gender
    FROM
        `avatar`
    WHERE
        avatar_id = '{avatar_id}'
        AND active = 1
        {query_where_email}
    """
    cursor.execute(query)
    return cursor.fetchone()


def get_avaturn_user_id(email: str):
    data = None
    db_connection = get_db_connection()
    with db_connection.cursor() as cursor:
        sql = """SELECT avaturn_user_id FROM `user` WHERE active = %s AND email = %s"""
        cursor.execute(sql, (True, email))
        result = cursor.fetchone()

        if result:
            if result["avaturn_user_id"] is None:
                res = avaturn.create_user()
                status_code = res["status_code"]

                if status_code == 200:
                    data = res["response"]["id"]

                    sql = """UPDATE `user` SET avaturn_user_id = %s WHERE email = %s"""
                    cursor.execute(sql, (data, email))
            else:
                data = result["avaturn_user_id"]
    db_connection.commit()
    db_connection.close()

    return data


@preprocessing_cursor
def get_character(character_id: str, cursor: object = None) -> dict:
    """character 테이블 데이터 조회

    :param character_id: 캐릭터 id
    :param cursor: pymysql.connect().cursor()

    :return: character 테이블 모든 데이터
    """
    item = {}
    query = f"SELECT * FROM `character` WHERE character_id = '{character_id}' AND active = 1"
    cursor.execute(query)
    item = cursor.fetchone()
    return item


def get_character_details(email: str, character_id: str):
    returncode = 0
    data = {}
    db_connection = get_db_connection()
    with db_connection.cursor() as cursor:
        cursor.execute(
            """SELECT
                name,
                description,
                CONCAT('/', thumbnail_file_path) AS thumbnail_file_path,
                show_persona
            FROM `character`
            WHERE character_id = %s AND email = %s""",
            (character_id, email),
        )
        result_char = cursor.fetchone()

        if result_char:
            data["character_name"] = result_char["name"]
            data["tag_line"] = result_char["description"]
            data["show_persona"] = result_char["show_persona"]
            data["profile_image"] = result_char["thumbnail_file_path"]

        cursor.execute(
            "SELECT basic_info, first_message, llm_type FROM `character_persona` WHERE character_id = %s ",
            (character_id),
        )
        result_char = cursor.fetchone()

        if result_char:
            data["persona"] = result_char["basic_info"]
            data["opening"] = result_char["first_message"]
            data["llm_type"] = result_char["llm_type"]

        returncode = 1

    return {"result": returncode, "data": data}


@preprocessing_cursor
def get_character_details_v2(character_id: str, cursor: object = None) -> dict:
    """캐릭터 세부 정보

    :param character_id: 캐릭터 id
    :param cursor: pymysql.connect().cursor()

    :return
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
        }
    """
    query = f"""
    SELECT
        C.character_id,
        C.created_time,
        C.name AS character_name,
        C.description,
        C.email,
        C.type,
        CONCAT('/', C.thumbnail_file_path) AS thumbnail_file_path,
        CP.first_message,
        CP.basic_info AS persona,
        CP.llm_type,
        CONCAT('/', A.avatar_file_path) AS avatar_file_path,
        CONCAT('/', A.thumbnail_file_path) AS avatar_thumbnail_file_path,
        A.gender AS avatar_gender
    FROM `character` AS C
    JOIN `character_persona` AS CP ON CP.character_id = C.character_id
    JOIN `avatar` AS A ON C.avatar_id = A.avatar_id AND A.active = 1
    WHERE
        C.active = 1
        AND C.character_id = '{character_id}'
    """
    cursor.execute(query)
    data = cursor.fetchone()
    if data:
        data["created_time"] = time.totimestamp(data["created_time"])
        data["avatar_idle_motion_file_path"] = (
            "/"
            + avatar_module.get_emotion_retargeting(
                "Idle", data["avatar_file_path"][1:], data["avatar_gender"]
            )
        )
    else:
        data = {}
    return data


@preprocessing_cursor
def get_comment(
    comment_id: int, character_id: str = None, cursor: object = None
) -> dict:
    """캐릭터 댓글을 ID로 조회

    :param comment_id: 댓글 id
    :param character_id: 캐릭터 id
    :param cursor: pymysql.connect().cursor()

    :return: character_comment 테이블에 들어있는 데이터셋
    """
    where_character_id = f"AND character_id = '{character_id}' " if character_id else ""
    query = f"SELECT * FROM `character_comment` WHERE comment_id = {comment_id} {where_character_id}AND active = 1"
    cursor.execute(query)
    return cursor.fetchone()


def get_persona_details(email: str, character_id: str):
    data = {}
    db_connection = get_db_connection()
    with db_connection.cursor() as cursor:
        sql = """
        SELECT
            C.name,
            CONCAT('/', C.thumbnail_file_path) AS thumbnail_file_path,
            C.description,
            C.show_persona,
            CP.basic_info,
            CP.first_message,
            (SELECT COUNT(*) FROM `character_like` as LC WHERE LC.`character_id` = C.`character_id`) as liked_count,
            U.name as creator_name,
            U.email as creator_id,
            (SELECT COUNT(*) FROM `character_like` as LC WHERE LC.character_id = C.character_id AND LC.email = %s) > 0 as is_liked
        FROM `character` as C
            JOIN `character_persona` as CP ON C.character_id = CP.character_id
            JOIN `user` as U ON C.email = U.email
        WHERE C.character_id = %s"""
        cursor.execute(sql, (email, character_id))
        result = cursor.fetchone()

        if result:
            data["character_name"] = result["name"]
            data["character_image"] = result["thumbnail_file_path"]
            data["creator_name"] = result["creator_name"]
            data["creator_id"] = result["creator_id"]
            data["is_liked"] = bool(result["is_liked"])
            data["liked_count"] = result["liked_count"]
            data["opening"] = result["first_message"]
            data["tag_line"] = result["description"]
            data["show_persona"] = bool(result["show_persona"])
            data["persona"] = result["basic_info"]
        else:
            return {"result": 0, "message": "There is no character data"}

    return data


def get_persona_details_v2(email: str, character_id: str):
    data = {}
    db_connection = get_db_connection()
    with db_connection.cursor() as cursor:
        sql = """
        SELECT
            C.name,
            CONCAT('/', C.thumbnail_file_path) AS thumbnail_file_path,
            C.description,
            C.show_persona,
            C.type,
            CP.basic_info,
            CP.first_message,
            (SELECT COUNT(*) FROM `character_like` as LC WHERE LC.character_id = C.character_id) as liked_count,
            U.name as creator_name,
            (SELECT COUNT(*) FROM `character_like` as LC WHERE LC.character_id = C.character_id AND LC.email = %s) > 0 as is_liked,
            ER.emoji_id,
            ER.emoji,
            ER.count,
            CASE
                WHEN ERL.email IS NOT NULL THEN TRUE
                ELSE FALSE
            END AS is_emoji_clicked_by_user,
            CS.content as comment_content,
            CS.writer as comment_writer,
            CT.total as comment_total,
            GG.briefing
        FROM `character` as C
        JOIN `character_persona` as CP ON C.character_id = CP.character_id
        JOIN `user` as U ON C.email = U.email
        LEFT JOIN (
            SELECT
                R.character_id,
                R.emoji_id,
                E.emoji,
                COUNT(R.emoji_id) as count
            FROM `emoji_reaction` as R
            JOIN `emoji` as E ON R.emoji_id = E.emoji_id
            WHERE R.character_id = %s
            GROUP BY R.emoji_id, E.emoji, R.character_id
        ) as ER ON C.character_id = ER.character_id
        LEFT JOIN (
            SELECT
                R.character_id,
                R.emoji_id,
                R.email
            FROM `emoji_reaction` as R
            WHERE R.character_id = %s AND R.email = %s
        ) as ERL ON C.character_id = ERL.character_id AND ER.emoji_id = ERL.emoji_id
        LEFT JOIN (
            SELECT
                CC.character_id,
                CC.content,
                CC.email as writer,
                COALESCE(COUNT(CCL.comment_id), 0) as like_count
            FROM `character_comment` as CC
            LEFT JOIN `character_comment_like` as CCL ON CC.comment_id = CCL.comment_id
            WHERE CC.character_id = %s AND CC.active = TRUE
            GROUP BY CC.character_id, CC.content, CC.email
            HAVING like_count >= 5
            ORDER BY like_count DESC
            LIMIT 1
        ) as CS ON C.character_id = CS.character_id
        LEFT JOIN (
            SELECT
                CC.character_id,
                COUNT(CC.comment_id) as total
            FROM `character_comment` as CC
            WHERE CC.character_id = %s AND CC.active = TRUE
            GROUP BY CC.character_id
        ) as CT ON C.character_id = CT.character_id
        LEFT JOIN (
            SELECT
                GG.character_id,
                GG.briefing
            FROM `guessing_game` as GG
            WHERE GG.character_id = %s
        ) as GG ON C.character_id = GG.character_id
        WHERE C.character_id = %s """
        cursor.execute(
            sql,
            (
                email,
                character_id,
                character_id,
                email,
                character_id,
                character_id,
                character_id,
                character_id,
            ),
        )
        results = cursor.fetchall()

        if results:
            result = results[0]
            data["character_name"] = result["name"]
            data["character_image"] = result["thumbnail_file_path"]
            data["creator_name"] = result["creator_name"]
            data["is_liked"] = bool(result["is_liked"])
            data["liked_count"] = result["liked_count"]
            data["type"] = result["type"]

            comment_map = {}
            comment_map["content"] = result["comment_content"]
            comment_map["writer"] = result["comment_writer"]
            comment_map["total"] = (
                result["comment_total"] if result["comment_total"] else 0
            )
            data["comment"] = comment_map

            emojis_arr = []
            for result in results:
                emojis_map = {}
                emojis_map["emoji_id"] = result["emoji_id"]
                emojis_map["emoji_type"] = result["emoji"]
                emojis_map["count"] = result["count"]
                emojis_map["is_clicked"] = bool(result["is_emoji_clicked_by_user"])
                emojis_arr.append(emojis_map)
            data["emojis"] = emojis_arr if result["emoji_id"] else []

            if result["type"] == "mystery":
                data["briefing"] = result["briefing"]
            else:
                data["opening"] = result["first_message"]
                data["tag_line"] = result["description"]
                data["show_persona"] = bool(result["show_persona"])
                data["persona"] = result["basic_info"]

    return data


def get_persona_enhanced(character_name: str, persona: str) -> dict:
    """AI를 통해 캐릭터 페르소나 증강 및 인사말 생성

    :param character_name: 캐릭터 이름
    :param persona: 캐릭터 페르소나

    :return
        {
            "persona": str,   # 증강된 페르소나
            "opening": str   # 생성된 인사말
        }
    """
    lambda_name = "heybee-persona-llmrevise"
    payload = {
        "prompt": persona
    }

    if character_name:
        payload["name"] = character_name

    # Lambda 함수 호출 및 응답 처리
    lambda_response = lambda_module.invoke(
        lambda_name,
        payload,
        use_alias=False
    )

    # Payload 스트리밍 본문 읽기
    payload_body = lambda_response.get("Payload", {}).get("body", {})
    if not payload_body:
        raise ValueError("Lambda response payload is missing")

    # # 스트리밍 본문을 문자열로 읽고 JSON 파싱
    # try:
    #     # 스트리밍 본문을 바이트로 읽고 UTF-8로 디코드
    #     body_string = payload_body.read().decode('utf-8')
    #     # JSON 문자열을 파이썬 딕셔너리로 파싱
    #     parsed_body = json.loads(body_string)
    # except json.JSONDecodeError as e:
    #     print(f"Error decoding JSON from Lambda response: {e}")
    #     print(f"Raw body string: {body_string}")  # 디버깅 위해 원본 출력
    #     raise ValueError(f"Failed to parse JSON response from Lambda: {e}")
    # except Exception as e:
    #     print(f"Error reading or decoding Lambda payload: {e}")
    #     raise

    # 파싱된 딕셔너리에서 값 추출
    return {
        "persona": payload_body.get("Prompt", ""),  # .get() 사용하여 혹시 모를 KeyError 방지
        "opening": payload_body.get("Opening", "")  # .get() 사용하여 혹시 모를 KeyError 방지
    }


def get_pre_signed_url(file_type: str, generate_type: str):
    data = {}
    uuid = shortuuid.ShortUUID().random(length=20)
    bucket_folder = ""
    file_name = ""
    bucket_name = const.S3_BUCKET_NAME[os.environ["AWS_REGION"]][
        os.environ["API_ALIAS"]
    ]

    if generate_type == "user":
        bucket_folder = "user_character/"
        file_name = bucket_folder + uuid + "." + file_type
    elif generate_type == "avaturn":
        bucket_folder = "avaturn_character/"
        file_name = bucket_folder + uuid + "." + file_type

    data["pre_signed_url"] = client.s3_client.generate_presigned_url(
        "put_object",
        Params={"Bucket": bucket_name, "Key": file_name},
        ExpiresIn=3600,
    )
    data["file_path"] = file_name

    return data


def get_signed_url(file_path: str) -> str:
    # TODO
    CLOUDFRONT_KEY_PAIR_ID = "KU7FY5R0VAJDW"
    cf_domain = const.CLOUDFRONT_DOMAIN[os.environ["AWS_REGION"]][
        os.environ["API_ALIAS"]
    ]
    url = cf_domain + "/" + file_path.strip("/")
    expire_date = datetime.utcnow() + timedelta(hours=1)
    cloudfront_signer = CloudFrontSigner(CLOUDFRONT_KEY_PAIR_ID, crypto.rsa_signer)
    signed_url = cloudfront_signer.generate_presigned_url(
        url, date_less_than=expire_date
    )
    return signed_url


def list_avatar(email: str = None, avatar_type: str = None) -> list:
    """아바타 리스트 조회.
    타입별로 조회 가능.
    타입 값 없을 경우 사용자가 조회 가능한 모든 아바타 조회.

    :param email: email
    :param avatar_type: 아바타 타입 (e.g. default)

    :return
        [
            {
                'avaturn_id': str,  (아바턴 id)
                'thumbnail': str,  (썸네일 S3 파일 경로)
                'file': str,  (아바타 파일 s3 파일 경로)
                'created_time': str,  (아바타 생성 시간 : 'YYYY-MM-DD hh:mm:ss')
                'gender': str,  (아바타 성별 : 'M' or 'F')
                'type': str || None,  (아바타 타입)
                'email': str  (아바타 생성/복제한 계정 이메일)
            },
            ...
        ]
    """
    ret = []
    s3_asset_cf_domain = ""
    db_connection = get_db_connection()
    with db_connection as db:
        cursor = db.cursor()

        # default 타입 기본적으로 포함
        select_default = f"""
        UNION
        SELECT
            avatar_id AS avaturn_id,
            CONCAT('{s3_asset_cf_domain}/', thumbnail_file_path) AS thumbnail,
            CONCAT('{s3_asset_cf_domain}/', avatar_file_path) AS file,
            created_time,
            gender,
            type,
            email
        FROM
            `avatar`
        WHERE
            active = 1
            AND type = '{const.AVATAR_TYPE_DEFAULT}'
        """

        where_email_avatar = ""
        where_email_copy = ""
        if email:
            where_email_avatar = f"AND A.email = '{email}'"
            where_email_copy = f"AND C.email = '{email}'"

        where_type = ""
        if avatar_type:
            where_type = f"AND A.type = '{avatar_type}'"
            select_default = ""
            if avatar_type == const.AVATAR_TYPE_DEFAULT:
                where_email_avatar = ""

        query = f"""
        SELECT
            A.avatar_id AS avaturn_id,
            CONCAT('{s3_asset_cf_domain}/', A.thumbnail_file_path) AS thumbnail,
            CONCAT('{s3_asset_cf_domain}/', A.avatar_file_path) AS file,
            A.created_time,
            A.gender,
            A.type,
            A.email
        FROM
            `avatar` AS A
        WHERE
            A.active = 1
            {where_email_avatar}
            {where_type}
        UNION
        SELECT
            C.avatar_id AS avaturn_id,
            CONCAT('{s3_asset_cf_domain}/', A.thumbnail_file_path) AS thumbnail,
            CONCAT('{s3_asset_cf_domain}/', A.avatar_file_path) AS file,
            A.created_time,
            A.gender,
            A.type,
            A.email
        FROM
            `character_copy` AS C
        JOIN
            `avatar` AS A
            ON A.avatar_id = C.avatar_id
        WHERE
            A.active = 1
            {where_email_copy}
            {where_type}
        {select_default}
        ORDER BY created_time DESC, avaturn_id
        """
        cursor.execute(query)
        ret = cursor.fetchall()

    return ret


def list_avatar_by_email(email: str):
    s3_asset_cf_domain = ""
    data = []
    db_connection = get_db_connection()
    with db_connection.cursor() as cursor:
        # 사용자가 생성한 아바타
        sql = """SELECT avatar_id, avatar_file_path, thumbnail_file_path, type FROM `avatar` WHERE email = %s AND active = TRUE AND post_processing = %s"""
        cursor.execute(sql, (email, 1))
        result = cursor.fetchall()

        for row in result:
            datamap = {}
            datamap["avaturn_id"] = row["avatar_id"]
            datamap["thumbnail"] = s3_asset_cf_domain + "/" + row["thumbnail_file_path"]
            datamap["file"] = s3_asset_cf_domain + "/" + row["avatar_file_path"]
            datamap["type"] = row["type"]
            data.append(datamap)

        # copy한 타사용자의 아바타
        copy_sql = """SELECT avatar_id FROM `character_copy` WHERE email = %s"""
        cursor.execute(copy_sql, (email,))
        copy_result = cursor.fetchall()

        for row in copy_result:
            character_sql = """SELECT avatar_file_path, thumbnail_file_path, type FROM `avatar` WHERE avatar_id = %s AND active = TRUE"""
            cursor.execute(character_sql, (row["avatar_id"]))
            character_result = cursor.fetchone()

            if character_result:
                datamap = {}
                datamap["avaturn_id"] = row["avatar_id"]
                datamap["thumbnail"] = (
                    s3_asset_cf_domain + "/" + character_result["thumbnail_file_path"]
                )
                datamap["file"] = (
                    s3_asset_cf_domain + "/" + character_result["avatar_file_path"]
                )
                datamap["type"] = ""
                data.append(datamap)

    return {"data": data}


@preprocessing_cursor
def list_character(
    email: str,
    page_size: int = 10,
    offset: int = 0,
    character_type: str = None,
    sort_by: str = None,
    search_keyword: str = None,
    like: bool = False,
    creator: str = None,
    cursor: object = None,
) -> dict:
    """캐릭터 리스트 조회
    미션게임 캐릭터는 character_type에 지정 했을 경우만 조회

    :param email: 조회 요청한 사용자 email (block 처리된 데이터 안보이게 하기 위해)
    :param page_size: page size for pagination
    :param offset: offset for pagination
    :param character_type: 캐릭터 타입 필터
    :param sort_by: 정렬 기준 (내림차순)
        - 'chat': 모든 사용자가 캐릭터에게 채팅 보낸 채팅 수
        - 'like': 좋아요
        - default(값 없을 경우): 캐릭터 생성 및 수정 시간
    :param search_keyword: 캐릭터 name, description 검색어
    :param like: 사용자가 좋아요 한 캐릭터만 조회할지 체크
        True: 좋아요 한 캐릭터만 조회
        False: 상관없이 다 조회
    :param creator: 캐릭터 생성자 email 필터 (default: 모든 생성자의 캐릭터 조회)
    :param cursor: pymysql.connect().cursor()

    :return
        [
            {
                'character_id': str,
                'character_name': str,
                'character_image': str,  (썸네일 파일 S3 경로)
                'character_desc': str,
                'create_username': str,  (생성한 사용자 계정 name)
                'liked_count': int,  (좋아요 수)
                'is_liked': bool,  (조회 요청한 사용자의 이 캐릭터 좋아요 유무)
                'type': str  (캐릭터 타입 e.g. 'user'  | 'celeb'  | 'preset'  | 'mystery'  | 'concept' | 'mission')
            }
        ]
    """
    conditions = ["C.type != 'mission'"]
    order_by = "C.modified_time DESC"

    # 좋아요 쿼리 추가
    if like:
        conditions.append("CLO.email IS NOT NULL")

    # 검색어 쿼리 추가
    if search_keyword:
        conditions.append(
            f"(UPPER(C.name) LIKE UPPER('%{search_keyword}%') OR UPPER(C.description) LIKE UPPER('%{search_keyword}%'))"
        )

        history_input = {
            "date": time.now().isoformat() + "Z",
            "email": email,
            "search_keyword": search_keyword,
        }

        table_name = "idolmaster_history_search"
        dynamodb.put_item(table_name, history_input)

    # 타입 조회 쿼리 추가
    if character_type:
        conditions = conditions[1:]  # mission 타입 제외 필터 삭제
        conditions.append(f"C.type = '{character_type}'")

    # 특정 사용자의 캐릭터 조회 쿼리 추가
    if creator:
        conditions.append(f"C.email = '{creator}'")

    # 정렬 기준 적용
    if sort_by == "like":
        order_by = "liked_count DESC, " + order_by
    elif sort_by == "chat":
        order_by = "C.total_usage_count DESC, " + order_by

    conditions_query = " AND " + " AND ".join(conditions) if conditions else ""
    query = f"""
    SELECT
        C.character_id,
        C.name AS character_name,
        C.description AS character_desc,
        CONCAT('/', C.thumbnail_file_path) AS character_image,
        U.name AS create_username,
        COUNT(CL.email) AS liked_count,
        C.type,
        IF (CLO.email IS NOT NULL, 1, 0) AS is_liked
    FROM
        `character` AS C
    LEFT JOIN
        `user` AS U
        ON C.email = U.email
    LEFT JOIN
        `character_like` AS CL
        ON C.character_id = CL.character_id
    LEFT JOIN
        `character_like` AS CLO
        ON C.character_id = CLO.character_id AND CLO.email = '{email}'
    WHERE
        C.active = TRUE
        {conditions_query}
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
        AND C.thumbnail_file_path NOT LIKE 'content%'
    GROUP BY C.character_id
    ORDER BY {order_by}
    LIMIT {page_size} OFFSET {offset}
    """
    cursor.execute(query)
    data = cursor.fetchall()
    for item in data:
        item["is_liked"] = bool(item["is_liked"])

    return data


def list_character_explore(email: str):
    data = []
    db_connection = get_db_connection()
    with db_connection.cursor() as cursor:
        sql = f"""
        SELECT
            character_id,
            name,
            description,
            email,
            CONCAT('/', thumbnail_file_path) AS thumbnail_file_path,
            type
        FROM `character`
        WHERE active = TRUE AND type IN ('concept', 'mystery')
            AND character_id NOT IN (
                SELECT character_id
                FROM `character_block`
                WHERE email = '{email}'
            )
            AND email NOT IN (
                    SELECT blocked_email
                    FROM `user_block`
                    WHERE email = '{email}'
            )
            AND thumbnail_file_path NOT LIKE 'content%'
        ORDER BY RAND() LIMIT 5
        """
        cursor.execute(sql)
        result = cursor.fetchall()

        for row in result:
            datamap = {}

            datamap["character_id"] = row["character_id"]
            datamap["character_name"] = row["name"]
            datamap["character_desc"] = row["description"]
            datamap["type"] = row["type"]

            create_useremail = row["email"]
            character_image_path = row["thumbnail_file_path"]

            # 캐릭터 썸네일 임시 url 생성
            # character_image = s3_asset_cf_domain + "/" + character_image_path
            character_image = character_image_path

            # 생성한 유저 이름 조회
            cursor.execute(
                "SELECT name FROM `user` WHERE email = %s", (create_useremail,)
            )
            user_result = cursor.fetchone()
            if user_result:
                create_username = user_result["name"]
            else:
                create_username = ""

            datamap["create_username"] = create_username
            datamap["character_image"] = character_image

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

    return data


def list_character_hot(email: str):
    returncode = 0
    data = []
    db_connection = get_db_connection()
    with db_connection.cursor() as cursor:
        cursor.execute(
            """SELECT character_id, name, description, email, thumbnail_file_path, type FROM `character` WHERE active = %s ORDER BY total_usage_count DESC LIMIT 10""",
            (True),
        )
        results = cursor.fetchall()

        for result in results:
            datamap = {}

            datamap["character_id"] = result["character_id"]
            datamap["character_name"] = result["name"]
            datamap["character_desc"] = result["description"]
            datamap["type"] = result["type"]

            # 캐릭터 썸네일 임시 url 생성
            character_image_path = result["thumbnail_file_path"]
            # character_image = gets3file(character_image_path, 180, False)
            character_image = "/" + character_image_path if character_image_path else None
            datamap["character_image"] = character_image

            # 생성한 유저 이름 조회
            cursor.execute(
                "SELECT name FROM `user` WHERE email = %s", (result["email"],)
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
                (result["character_id"]),
            )
            like_count_result = cursor.fetchone()

            datamap["liked_count"] = int(like_count_result["COUNT(*)"])

            # 좋아요 여부
            cursor.execute(
                "SELECT COUNT(*) FROM `character_like` WHERE email = %s AND character_id = %s",
                (email, result["character_id"]),
            )
            is_like_result = cursor.fetchone()

            is_liked = False

            if is_like_result["COUNT(*)"] > 0:
                is_liked = True

            datamap["is_liked"] = is_liked

            data.append(datamap)

        returncode = 1

    return {"result": returncode, "data": data}


def list_character_type(email: str, character_type: str):
    data = []
    db_connection = get_db_connection()
    with db_connection.cursor() as cursor:
        sql = """
        SELECT
            character_id,
            name,
            description,
            email,
            CONCAT('/', thumbnail_file_path) AS thumbnail_file_path
        FROM `character`
        WHERE active = TRUE
            AND type = %s
            AND NOT EXISTS (
                SELECT 1
                FROM `character_block`
                WHERE character_block.character_id = `character`.character_id
                AND character_block.email = %s
            )
            AND NOT EXISTS (
                SELECT 1
                FROM `user_block`
                WHERE user_block.blocked_email = `character`.email
                AND user_block.email = %s
            )
        """
        cursor.execute(sql, (character_type, email, email))
        results = cursor.fetchall()

        if results:
            for result in results:
                datamap = {}

                datamap["character_id"] = result["character_id"]
                datamap["character_name"] = result["name"]
                datamap["character_desc"] = result["description"]
                datamap["type"] = character_type
                datamap["character_image"] = result["thumbnail_file_path"]

                # 생성한 유저 이름 조회
                cursor.execute(
                    "SELECT name FROM `user` WHERE email = %s", (result["email"],)
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
                    (result["character_id"]),
                )
                like_count_result = cursor.fetchone()

                datamap["liked_count"] = int(like_count_result["COUNT(*)"])

                # 좋아요 여부
                cursor.execute(
                    "SELECT COUNT(*) FROM `character_like` WHERE email = %s AND character_id = %s",
                    (email, result["character_id"]),
                )
                is_like_result = cursor.fetchone()

                is_liked = False

                if is_like_result["COUNT(*)"] > 0:
                    is_liked = True

                datamap["is_liked"] = is_liked

                data.append(datamap)

    return {"data": data}


def list_comment(
    email: str, character_id: str, sort_by: str, page_size: int, offset: int
):
    data = []
    total = 0
    db_connection = get_db_connection()
    with db_connection.cursor() as cursor:
        sql = """
            SELECT
                character_comment.comment_id,
                character_comment.content,
                character_comment.created_time,
                COUNT(DISTINCT like_count_alias.email) AS like_count,
                CASE
                    WHEN (is_liked_alias.email IS NOT NULL) THEN TRUE
                    ELSE FALSE
                END AS is_liked,
                user.name AS writer,
                CASE
                    WHEN (character_comment.email = %s) THEN TRUE
                    ELSE FALSE
                END AS is_writer,
                (SELECT COUNT(*)
                    FROM `character_comment`
                    WHERE character_comment.character_id = %s
                    AND character_comment.active IS TRUE) AS total_comments
            FROM
                `character_comment`
            LEFT JOIN
                `character_comment_like` AS like_count_alias
                ON character_comment.comment_id = like_count_alias.comment_id
            LEFT JOIN
                `character_comment_like` AS is_liked_alias
                ON character_comment.character_id = is_liked_alias.character_id
                AND character_comment.comment_id = is_liked_alias.comment_id
                AND is_liked_alias.email = %s
            LEFT JOIN
                `user`
                ON character_comment.email = user.email
            WHERE
                character_comment.character_id = %s
                AND character_comment.active IS TRUE
            GROUP BY
                character_comment.comment_id,
                character_comment.content,
                character_comment.created_time,
                user.name,
                is_liked_alias.email,
                character_comment.email
        """
        if sort_by == "newest":
            sql += " ORDER BY character_comment.created_time DESC"
        elif sort_by == "top":
            sql += " ORDER BY like_count DESC, character_comment.created_time DESC"

        sql += " LIMIT %s OFFSET %s"

        cursor.execute(
            sql, (email, character_id, email, character_id, page_size, offset)
        )
        results = cursor.fetchall()

        for result in results:
            data_map = {}
            data_map["comment_id"] = result["comment_id"]
            data_map["writer"] = result["writer"]
            data_map["content"] = result["content"]
            data_map["created_time"] = result["created_time"].isoformat()
            data_map["is_liked"] = result["is_liked"]
            data_map["like_count"] = result["like_count"]
            data_map["is_liked"] = bool(result["is_liked"])
            data_map["is_writer"] = bool(result["is_writer"])
            data.append(data_map)
            total = result["total_comments"]

    return {"comments": data, "total_count": total}


@preprocessing_cursor
def list_types(cursor: object = None) -> list:
    """캐릭터 타입 리스트 조회

    :param cursor: pymysql.connect().cursor()

    :return
        [
            {
                'type': str,  (타입 이름)
                'description': str  (타입 설명)
            },
            ...
        ]
    """
    query = "SELECT type, description FROM `character_type`"
    cursor.execute(query)
    return cursor.fetchall()


def post_emoji(email: str, character_id: str, emoji_id: int):
    db_connection = get_db_connection()
    with db_connection.cursor() as cursor:
        # 기존 반응 체크
        cursor.execute(
            """SELECT COUNT(*) as reaction_exists FROM `emoji_reaction` WHERE character_id = %s AND email = %s AND emoji_id = %s""",
            (character_id, email, emoji_id),
        )
        existing_reaction = cursor.fetchone()

        if existing_reaction["reaction_exists"] > 0:
            pass
        else:
            insert_query = """
                INSERT INTO `emoji_reaction` (character_id, email, emoji_id)
                VALUES (%s, %s, %s)
            """
            cursor.execute(insert_query, (character_id, email, emoji_id))

    db_connection.commit()
    db_connection.close()


def put_thumbnail_s3(file_object: object, extension: str = "png") -> str:
    """S3에 썸네일 파일 저장.

    :param file_object: 이미지 파일 (Bytes)
    :param extension: 이미지 파일 확장자
        - 기본값 png인 이유: 아바타 썸네일 저장 시 무조건 png로 저장하는 기존 코드를 수정 안하기 위해

    :return: 저장된 S3 파일 경로
    """
    uuid = shortuuid.ShortUUID().random(length=20)
    file_path = f"user_character/{uuid}.{extension}"
    bucket_name = const.S3_BUCKET_NAME[os.environ["AWS_REGION"]][
        os.environ["API_ALIAS"]
    ]
    client.s3_client.put_object(Bucket=bucket_name, Key=file_path, Body=file_object)
    print(f"S3 put_object {bucket_name} {file_path}")
    return file_path


def save_avatar(
    create_user: str,  # email
    avaturn_id: str,
    model_file_path: str,  # s3 path ("" 또는 "user_character/~.glb")
    thumbnail_file_path: str,
    gender: str,
):
    if not thumbnail_file_path:
        thumbnail_file_path = f"avaturn_character/{avaturn_id}.jpg"

    # user
    if model_file_path.startswith("user_character/"):
        pass
    # avaturn
    else:
        model_file_path = f"avaturn_character/{avaturn_id}.glb"

    # payload = {
    #     'method': 'apply_motion',
    #     'params': {
    #         "avatar_id": avaturn_id,
    #         "env_name": os.environ['API_ALIAS'],
    #         "avatar_file_path": model_file_path
    #     }
    # }
    # response = client.lambda_client.invoke(
    #     FunctionName=f"idolmaster-external-api:{os.environ['API_ALIAS']}",
    #     Payload=json.dumps(payload)
    # )
    # response = json.loads(response["Payload"].read())
    # print(f"avatar motion apply : {avaturn_id} {os.environ['API_ALIAS']}, response.status : {response['statusCode']}")
    # if response['statusCode'] == 200:
    db_connection = get_db_connection()
    with db_connection.cursor() as cursor:
        sql = """
        INSERT INTO `avatar` (avatar_id, email, avatar_file_path, thumbnail_file_path, active, gender, post_processing)
        VALUES (%s, %s, %s, %s, %s, %s, 1)
        """
        cursor.execute(
            sql,
            (
                avaturn_id,
                create_user,
                model_file_path,
                thumbnail_file_path,
                True,
                gender,
            ),
        )
    db_connection.commit()
    db_connection.close()
    # else:
    #     return {"result": 0, 'message': 'Failed to aplly avatar motion'}


def set_like_comment(email: str, character_id: str, comment_id: str):
    db_connection = get_db_connection()
    with db_connection.cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) as comment_exists FROM `character_comment_like` WHERE character_id = %s AND comment_id = %s AND email = %s",
            (character_id, comment_id, email),
        )
        comment_like_check = cursor.fetchone()
        if comment_like_check["comment_exists"] == 0:
            sql = """
                INSERT INTO `character_comment_like` (character_id, email, comment_id)
                VALUES (%s, %s, %s)
            """
            cursor.execute(sql, (character_id, email, comment_id))

    db_connection.commit()


def set_unlike_comment(email: str, character_id: str, comment_id: str):
    db_connection = get_db_connection()
    with db_connection.cursor() as cursor:
        # 댓글 좋아요 존재 여부 확인
        cursor.execute(
            "SELECT COUNT(*) as comment_exists FROM `character_comment_like` WHERE character_id = %s AND comment_id = %s AND email = %s",
            (character_id, comment_id, email),
        )
        comment_like_check = cursor.fetchone()

        if comment_like_check["comment_exists"] > 0:
            # 좋아요 삭제
            sql = """
                DELETE FROM `character_comment_like`
                WHERE character_id = %s AND comment_id = %s AND email = %s
            """
            cursor.execute(sql, (character_id, comment_id, email))

    db_connection.commit()
    db_connection.close()


def update_like_character(email: str, character_id: str, like: bool):
    db_connection = get_db_connection()
    with db_connection.cursor() as cursor:
        if like:
            # 좋아요 등록
            cursor.execute(
                "SELECT COUNT(*) FROM `character_like` WHERE email = %s AND character_id = %s",
                (
                    email,
                    character_id,
                ),
            )
            result = cursor.fetchone()
            if not result["COUNT(*)"]:
                sql = """INSERT INTO `character_like` (`email`, `character_id`) VALUES (%s, %s)"""
                cursor.execute(sql, (email, character_id))

        else:
            # 좋아요 취소
            cursor.execute(
                "SELECT COUNT(*) FROM `character_like` WHERE email = %s AND character_id = %s",
                (
                    email,
                    character_id,
                ),
            )
            result = cursor.fetchone()
            if result["COUNT(*)"] > 0:
                sql = """DELETE FROM `character_like` WHERE email = %s AND character_id = %s"""
                cursor.execute(sql, (email, character_id))

    db_connection.commit()
    db_connection.close()


# def get_asset_store_character_motion_url(file_id: str, file_type: str):
#     data = None
#     s3_asset_cf_domain = ''
#     db_connection = get_db_connection()
#     with db_connection.cursor() as cursor:
#         if file_type == 'character':
#             cursor.execute("SELECT avatar_file_path FROM `avatar` WHERE avatar_id = %s", (file_id,))
#             result = cursor.fetchone()
#             data = s3_asset_cf_domain + "/" + result["avatar_file_path"]

#         elif file_type == 'motion':
#             cursor.execute("SELECT motion_file_path FROM `asset_store_motion` WHERE id = %s", (file_id,))
#             result = cursor.fetchone()
#             data = s3_asset_cf_domain + "/" + result["motion_file_path"]

#         else:
#             return {"result": 0, "message": "No such type."}

#     return {"data": data}


# def list_avatar_asset():
#     s3_asset_cf_domain = ''
#     data = [
#         {
#             'id': '018fbd05-36f5-73c4-a309-57868b18fc3f',
#             'thumbnail': s3_asset_cf_domain + '/' + 'preset_character/Elon_musk_at_action.png'
#         },
#         {
#             'id': '018fbd06-0ddd-7daa-927e-bbe7154ced02',
#             'thumbnail': s3_asset_cf_domain + '/' + 'preset_character/Joy_at_action.png'
#         }
#     ]
#     return {"data": data}


# def list_avatar_store_motion():
#     data = []
#     s3_asset_cf_domain = ''
#     db_connection = get_db_connection()
#     with db_connection.cursor() as cursor:
#         cursor.execute("SELECT * FROM `asset_store_motion`")
#         motion_result = cursor.fetchall()

#         for row in motion_result:
#             datamap = {}
#             motion_id = row['id']
#             datamap["thumbnail"] = s3_asset_cf_domain + "/" + row['thumbnail_file_path']
#             datamap["name"] = row['thumbnail_file_path'].split("/")[1].rsplit('.', 1)[0]
#             datamap["id"] = motion_id
#             data.append(datamap)

#     return {"data": data}
