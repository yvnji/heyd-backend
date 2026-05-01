from decimal import Decimal
import json
import os
import random
import traceback
from boto3.dynamodb.conditions import Key

from google.auth.transport.requests import Request
from google.oauth2 import service_account

import const
from lib import client
from lib import http_request
from lib import time
from service import avatar as avatar_module
from service import product as product_module
from thirdparty import dynamodb
from thirdparty import llm_api
from thirdparty import secretmanager
from thirdparty.mariadb import get_db_connection


def check_connection(connectionId, endpoint_url):
    api_client = client.apigatewaymanagementapi_client(endpoint_url)
    is_alive = None
    try:
        data = json.dumps({"action": "test"}).encode("utf-8")
        api_client.post_to_connection(ConnectionId=connectionId, Data=data)
        is_alive = True
    except api_client.exceptions.GoneException:
        is_alive = False

    return is_alive


def get_access_token():
    # 자격 증명 생성
    secret_item = json.loads(secretmanager.get_secret())
    credentials = service_account.Credentials.from_service_account_info(
        json.loads(secret_item["FIREBASE_SERVICE_ACCOUNT"]),
        scopes=["https://www.googleapis.com/auth/firebase.messaging"],
    )
    credentials.refresh(Request())
    return credentials.token


def gets3file(filepath, expiresec, removeURL):
    """S3 임시 url 생성"""
    # file_path = preset_character/ElonMusk_idle.glb
    # result = s3.generate_presigned_url(
    #     "get_object",
    #     Params={"Bucket": s3_bucket_name, "Key": filepath},
    #     ExpiresIn=expiresec,
    # )
    # if removeURL:
    #     result = result.replace(s3_bucket_url, "")

    if os.environ["API_ALIAS"] == const.ALIAS_PROD:
        result = f"https://asset.hey-d.ai/{filepath}"
    else:
        result = f"/{filepath}"
    return result


def is_blocked(user_email, character_id, creator_email):
    sql = """
    SELECT COUNT(*) as count FROM (
        SELECT email, character_id FROM `character_block` WHERE email = %s AND character_id = %s
        UNION
        SELECT email, blocked_email FROM `user_block` WHERE email = %s AND blocked_email = %s
    ) AS block_check
    """
    result = None
    db_connect = get_db_connection()
    with db_connect.cursor() as cursor:
        cursor.execute(sql, (user_email, character_id, user_email, creator_email))
        result = cursor.fetchone()
    db_connect.close()
    return result and result["count"] > 0


def join_game_chat(connection_id: str, email: str, game_chat_id: int) -> None:
    """채팅방 연결 정보 등록"""
    utc_now_iso = time.now().isoformat() + "Z"
    db_connection = get_db_connection()
    with db_connection as db:
        cursor = db.cursor()
        query = f"""
            INSERT INTO `mission_game_chat_connection` (`game_chat_id`, `connection_id`, `last_connection_time`, `email`)
            VALUES ({game_chat_id}, '{connection_id}', '{utc_now_iso}', '{email}')
            ON DUPLICATE KEY UPDATE
                `connection_id` = VALUES(`connection_id`),
                `last_connection_time` = VALUES(`last_connection_time`)
        """
        cursor.execute(query)
        db.commit()


def join_groupchat(connection_id: str, email: str, groupchat_id: str):
    # 채팅방 연결 정보 등록
    utc_now_iso = time.now().isoformat() + "Z"
    db_connection = get_db_connection()
    with db_connection.cursor() as cursor:
        sql = """
            INSERT INTO `groupchat_connection` (`groupchat_id`, `connection_id`, `last_connection_time`, `email`)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                `connection_id` = VALUES(`connection_id`),
                `last_connection_time` = VALUES(`last_connection_time`)
        """
        cursor.execute(sql, (groupchat_id, connection_id, utc_now_iso, email))
    db_connection.commit()
    db_connection.close()


def join_chat(connection_id: str, email: str, chatroom_id: str):
    # 채팅방 연결 정보 등록
    utc_now_iso = time.now().isoformat() + "Z"
    db_connection = get_db_connection()
    with db_connection.cursor() as cursor:
        sql = """
            INSERT INTO `chat_connection` (`chat_id`, `connection_id`, `last_connection_time`, `email`)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                `connection_id` = VALUES(`connection_id`),
                `last_connection_time` = VALUES(`last_connection_time`)
        """
        cursor.execute(sql, (chatroom_id, connection_id, utc_now_iso, email))
    db_connection.commit()
    db_connection.close()


def send_message_chat(
    connection_id: str,
    domain_name: str,
    email: str,
    chatroom_id: str,
    message: str,
    chat_id: str,
):
    utc_now_iso = time.now().isoformat() + "Z"
    timestamp_at = str(round(Decimal(time.timestampnow()), 5))

    # 웹소켓 연결
    url = "https://" + domain_name + "/" + os.environ["API_ALIAS"]
    apigatewaymanagementapi = client.apigatewaymanagementapi_client(url)

    # check dart
    check_dart = product_module.decrease_product(
        email, const.PRODUCT_CHARGE_TYPE_DEDUCT_MESSAGE
    )
    if not check_dart["result"]:
        # 캐릭터 조회 및 메세지 전송
        db_connection = get_db_connection()
        with db_connection.cursor() as cursor:
            cursor.execute(
                """
            SELECT charact.*, persona.first_message, persona.basic_info, 'llama3-70b-instruct' as llm_type, ava.avatar_file_path, char_llm.main_prompt, '80' as top_k, '0.95' as temperature, char_llm.options
            FROM `character` AS charact, `character_persona` AS persona, `avatar` AS ava, `character_llm` AS char_llm
            WHERE charact.`character_id` = (SELECT member_id FROM `chat_member` WHERE `chat_id` = %s AND is_user = FALSE)
            AND persona.`character_id` = charact.`character_id` AND charact.avatar_id = ava.avatar_id
            """,
                (chatroom_id,),
            )
            char_result = cursor.fetchone()
            apigatewaymanagementapi.post_to_connection(
                ConnectionId=connection_id,
                Data=json.dumps(
                    {
                        "status_code": 2,
                        "chatroom_uuid": chatroom_id,
                        "send_time": utc_now_iso,
                        "id": char_result["character_id"],
                        "msg": "Not enough darts to proceed.",
                        "dart": check_dart["remain"]["dart"],
                    }
                ),
            )
        db_connection.close()
        print("No dart")
        return False

    chat_table_name = "idolmaster_chat"
    print("message before : ", message)
    message = message.replace("\xa0", " ")
    print("message after : ", message)
    # 채팅내역 저장
    chat = {
        "chatroom_uuid": chatroom_id,
        "send_time": timestamp_at,
        "id": email,
        "msg": message,
    }
    dynamodb.put_item(chat_table_name, chat)

    # 데이터 선언
    data_json = {
        "msg": message,
        "id": email,
        "send_time": utc_now_iso,
        "chat_id": chat_id,
        "dart": check_dart["remain"]["dart"],
    }

    db_connection = get_db_connection()
    with db_connection.cursor() as cursor:
        # 최신 채팅시각 저장
        sql = "UPDATE `chat_member` SET `last_send_time` = %s WHERE `chat_id` = %s AND `member_id` = %s "
        cursor.execute(sql, (timestamp_at, chatroom_id, email))

        # 사용자 자신에게 해당 소켓 전달 (메세지가 잘 전달되었는 확인용도)
        sql = "SELECT connection_id FROM `chat_connection` WHERE chat_id = %s"
        cursor.execute(sql, (chatroom_id))
        connections = cursor.fetchone()
        if connections:
            try:
                apigatewaymanagementapi.post_to_connection(
                    ConnectionId=connections["connection_id"],
                    Data=json.dumps(data_json),
                )
            except apigatewaymanagementapi.exceptions.GoneException:
                print("Connection is gone.")
            except Exception:
                print(
                    " ====== ‼️ send post_to_connection ERROR: {} ======".format(
                        traceback.format_exc()
                    )
                )

    db_connection.commit()
    db_connection.close()
    return True


def send_message_chat_ai(
    domain_name: str,
    connection_id: str,
    chatroom_id: str,
    character_type: str,
    safe_chat: bool,
):
    # 캐릭터& 유저 정보 가져오기
    character_profiles = []
    user_profiles = []
    expression_keys = []
    url = "https://" + domain_name + "/" + os.environ["API_ALIAS"]
    apigatewaymanagementapi = client.apigatewaymanagementapi_client(url)
    db_connection = get_db_connection()
    with db_connection:
        with db_connection.cursor() as cursor:
            cursor.execute(
                """
            SELECT charact.*, persona.first_message, persona.basic_info, 'llama3-70b-instruct' as llm_type, ava.avatar_file_path, ava.gender, char_llm.main_prompt, '80' as top_k, '0.95' as temperature, char_llm.options
            FROM `character` AS charact, `character_persona` AS persona, `avatar` AS ava, `character_llm` AS char_llm
            WHERE charact.`character_id` = (SELECT member_id FROM `chat_member` WHERE `chat_id` = %s AND is_user = FALSE)
            AND persona.`character_id` = charact.`character_id` AND charact.avatar_id = ava.avatar_id
            """,
                (chatroom_id,),
            )
            char_result = cursor.fetchone()
            character_profiles.append(char_result)
            cursor.execute(
                """SELECT A.*, B.notification, C.`connection_id`
            FROM `user` AS A, `chat_member` AS B, `chat_connection` AS C
            WHERE B.`chat_id` = %s AND A.email = B.member_id AND B.`chat_id` = C.`chat_id`
            AND A.email = C.email AND B.is_user = TRUE AND B.active = TRUE
            """,
                (chatroom_id,),
            )
            user_result = cursor.fetchone()
            user_profiles.append(user_result)
            cursor.execute(
                "SELECT type, type AS name, 1 AS duration, Eyelash_Mesh, Eyes_Mesh, Teeth_Mesh, Tongue_Mesh, EyeAO_Mesh, Head_Mesh FROM `avatar_expression_face`"
            )
            expression_keys.append(cursor.fetchall())

    # 채팅 정보 가져오기
    chat_table_name = "idolmaster_chat"
    chat_tb = dynamodb.get_resource_obj(chat_table_name)
    chat_histories = chat_tb.query(
        KeyConditionExpression=Key("chatroom_uuid").eq(chatroom_id),
        ScanIndexForward=False,
        Limit=150,
    )["Items"]

    # API 요청 합성
    print(f"character_profiles: {character_profiles}")
    list_content = llm_api.content_merge_chat(
        character_profiles[0], user_profiles[0], chat_histories, os.environ["API_ALIAS"]
    )

    # OpenAI API 생성 & 답변 추출
    answer, analysis_emotion, block_reason = llm_api.call_llm_chat(
        "gpt-4o",
        list_content,
        "",
        character_profiles[0]["llm_type"],
        character_profiles[0]["top_k"],
        character_profiles[0]["temperature"],
        character_profiles[0]["options"],
        os.environ["API_ALIAS"],
        character_type,
        safe_chat,
    )
    print(f"answer: {answer}")
    print(f"analysis_emotion: {analysis_emotion}")
    print(f"block_reason: {block_reason}")

    # 채팅 DB에 답변 저장
    timestamp_at = str(round(Decimal(time.timestampnow()), 5))

    answer_item = {
        "chatroom_uuid": chatroom_id,
        "send_time": timestamp_at,
        "id": character_profiles[0]["character_id"],
        "msg": answer,
    }
    dynamodb.put_item(chat_table_name, answer_item)

    # 최신 채팅시각 저장 & 캐릭터 사용 횟수 업데이트
    db_connection = get_db_connection()
    with db_connection:
        with db_connection.cursor() as cursor:
            cursor.execute(
                "UPDATE `chat_member` SET `last_send_time` = %s WHERE `chat_id` = %s AND `member_id` = %s ",
                (timestamp_at, chatroom_id, character_profiles[0]["character_id"]),
            )
            cursor.execute(
                "UPDATE `character` SET total_usage_count = total_usage_count+1 WHERE `character_id` = %s",
                (character_profiles[0]["character_id"],),
            )
            db_connection.commit()

    # Emotion shapekey 포함
    emotions = []
    for expression_key in expression_keys[0]:
        if expression_key["type"] == analysis_emotion:
            temp_map = {}
            data_map = {}
            for k, v in expression_key.items():
                if v is not None and k != "type" and k != "name" and k != "duration":
                    temp_map[k] = json.loads(v)
                elif k == "type" or k == "name" or k == "duration":
                    data_map[k] = v
                else:
                    temp_map[k] = v
            data_map["value"] = temp_map
            emotions.append(data_map)
            print(f"emotions: {emotions}")
    if len(emotions) > 0:
        answer_item["expression"] = random.choice(emotions)
    else:
        answer_item["expression"] = None

    # Motion 포함
    answer_item["motion_url"] = None
    character_file_name = (
        character_profiles[0]["avatar_file_path"]
        .split("/")[1]
        .replace(".glb", "")
        .replace(".gltf", "")
    )
    print(character_file_name)
    # if stage == 'dev':
    #     motion_data = s3.list_objects_v2(Bucket=s3_bucket_name, Prefix='motion_unity/'+character_file_name+'/stand/'+analysis_emotion)
    #     print('Prefix : ','motion_unity/'+character_file_name+'/stand/'+analysis_emotion)
    # else:

    # 추리게임 로봇인 경우에는 무조건 Neutral 모션
    if character_file_name == "robot_ava":
        analysis_emotion = "Neutral"

    # Emotion file path
    motion_path = avatar_module.get_emotion_retargeting(
        analysis_emotion,
        character_profiles[0]["avatar_file_path"],
        character_profiles[0]["gender"],
    )
    answer_item["motion_url"] = "/" + motion_path
    print("motion file path :", answer_item["motion_url"])

    # motion_data = client.s3_client.list_objects_v2(
    #     Bucket=const.S3_BUCKET_NAME[os.environ['AWS_REGION']][os.environ['API_ALIAS']],
    #     Prefix='motion/'+character_file_name+'/'+analysis_emotion)
    # print('motion_data : ',motion_data)
    # if 'Contents' in motion_data:
    #     motion_files = [file['Key'] for file in motion_data['Contents'] if not file['Key'].endswith('/')]
    #     print(motion_files)
    #     if motion_files:
    #         file_path = random.choice(motion_files)
    #         answer_item["motion_url"] = gets3file(file_path, 7200, True)
    #         print(answer_item["motion_url"])

    # 채팅방에 전송
    try:
        answer_item["status_code"] = 1
        apigatewaymanagementapi.post_to_connection(
            ConnectionId=user_profiles[0]["connection_id"],
            Data=json.dumps(answer_item),
        )
    except apigatewaymanagementapi.exceptions.GoneException:
        print("Connection is gone.")
    except Exception:
        print(" ====== (websocket-sendAI) R: {} ======".format(traceback.format_exc()))

    # 사용자가 채팅방 접속해있지 않을 경우 푸시알림
    endpoint_url = "https://" + domain_name + "/" + os.environ["API_ALIAS"]
    is_alive = check_connection(connection_id, endpoint_url)
    if is_alive is False:
        if user_profiles[0]["notification"] == 1:
            if user_profiles[0]["fcm_token"]:
                send_push(
                    user_profiles[0]["fcm_token"],
                    character_profiles[0]["name"],
                    answer,
                    "chat/" + chatroom_id,
                )


def send_message_game_chat(
    connection_id: str,
    domain_name: str,
    email: str,
    game_chat_id: int,
    message: str,
    character_uuid: str,
    chat_id: str,
) -> bool:
    """미션게임 채팅방에 메세지 전송

    :param connection_id: 웹소켓 connection id
    :param domain_name: 웹소켓 domain name
    :param email: 메세지 전송하는 사용자 email
    :param game_chat_id: 전송하는 미션게임 채팅방 id
    :param message: 전송 메세지
    :param character_uuid: 메세지를 수신할 채팅방 내에 있는 캐릭터 id
    :param chat_id: 사용자가 보낸 채팅 id

    :return
        True: 메세지 전송 성공 (다트 있을 경우)
        False: 메세지 전송 실패 (다트 없을 경우)
    """
    res = False

    # 웹소켓 연결
    endpoint_url = "https://" + domain_name + "/" + os.environ["API_ALIAS"]
    apigatewaymanagementapi = client.apigatewaymanagementapi_client(endpoint_url)

    db_connection = get_db_connection()
    with db_connection as db:
        cursor = db.cursor()

        # check dart
        check_dart = product_module.decrease_product(
            email, const.PRODUCT_CHARGE_TYPE_DEDUCT_MESSAGE, cursor=cursor
        )
        if check_dart["result"]:
            utc_now_iso = time.now().isoformat() + "Z"
            timestamp_at = str(round(Decimal(time.timestampnow()), 5))

            # 채팅내역 저장
            print("message before : ", message)
            message = message.replace("\xa0", " ")
            print("message after : ", message)
            insert_chat = {
                "chat_id": game_chat_id,
                "send_time": timestamp_at,
                "id": email,
                "msg": message,
            }
            dynamodb.put_item("idolmaster_game_chat", insert_chat)

            # 최신 채팅시각 업데이트
            sql = f"""
            UPDATE
                `chatroom_member`
            SET
                `last_send_time` = '{timestamp_at}'
            WHERE
                `game_chat_id` = {game_chat_id} AND `character_id` = '{character_uuid}'
            """
            cursor.execute(sql)

            # 데이터 선언
            data_json = {
                "msg": message,
                "id": email,
                "send_time": utc_now_iso,
                "game_chat_id": game_chat_id,
                "dart": check_dart["remain"]["dart"],
                "chat_id": chat_id,
            }

            # 채팅방에 전송
            sql = f"""
            SELECT
                connection_id
            FROM
                `mission_game_chat_connection`
            WHERE
                game_chat_id = {game_chat_id}
            """
            cursor.execute(sql)
            connections = cursor.fetchall()

            for con in connections:
                try:
                    apigatewaymanagementapi.post_to_connection(
                        ConnectionId=con["connection_id"],
                        Data=json.dumps(data_json),
                    )
                except apigatewaymanagementapi.exceptions.GoneException:
                    print("Connection is gone.")
                except Exception:
                    print(
                        " ====== ‼️ groupsend ERROR: {} ======".format(
                            traceback.format_exc()
                        )
                    )
            res = True

        else:
            try:
                # 메세지 전송
                apigatewaymanagementapi.post_to_connection(
                    ConnectionId=connection_id,
                    Data=json.dumps(
                        {
                            "status_code": 2,
                            "game_chat_id": game_chat_id,
                            "send_time": utc_now_iso,
                            "id": character_uuid,
                            "msg": "Not enough darts to proceed.",
                            "dart": check_dart["remain"]["dart"],
                            "chat_id": chat_id,
                        }
                    ),
                )
            except apigatewaymanagementapi.exceptions.GoneException:
                print("Connection is gone.")
            except Exception:
                print(
                    " ====== ‼️ groupsend ERROR: {} ======".format(
                        traceback.format_exc()
                    )
                )
            print("No dart")

        db.commit()
    return res


def send_message_game_chat_ai(
    domain_name: str, game_chat_id: int, character_uuid: str, safe_chat: bool
) -> None:
    """미션게임 채팅방에 캐릭터 AI 메세지 전송

    :param domain_name: 웹소켓 domain name
    :param game_chat_id: 전송하는 미션게임 채팅방 id
    :param character_uuid: 메세지를 수신할 채팅방 내에 있는 캐릭터 id
    :param safe_chat: safe chat 적용 여부
    """

    # 웹소켓 연결
    url = "https://" + domain_name + "/" + os.environ["API_ALIAS"]
    apigatewaymanagementapi = client.apigatewaymanagementapi_client(url)
    character_profile = {}
    character_profile_other = {}
    expression_keys = []

    db_connection = get_db_connection()
    with db_connection as db:
        cursor = db.cursor()
        query = f"""
        SELECT
            C.*,
            P.first_message,
            P.basic_info,
            'llama3-70b-instruct' AS llm_type,
            A.avatar_file_path,
            A.gender,
            '80' AS top_k,
            '0.95' AS temperature,
            (SELECT options FROM `character_llm` WHERE llm_type = 'llama3-70b-instruct') AS options,
            GCM.name AS room_name,
            G.mission_info,
            G.overview,
            G.title
        FROM
            `chatroom_member` AS CM
        JOIN
            `character` AS C
            ON CM.character_id = C.character_id
        JOIN
            `character_persona` AS P
            ON P.character_id = C.character_id
        JOIN
            `avatar` AS A
            ON C.avatar_id = A.avatar_id
        JOIN
            `mission_game_chat` as GC
            ON GC.id = CM.game_chat_id
        JOIN
            `mission_game_chat_meta` as GCM
            ON GCM.id = GC.meta_id
        JOIN
            `mission_game` as G
            ON GCM.game_id = G.id
        WHERE
            CM.game_chat_id = {game_chat_id}
            AND CM.email IS NULL
            AND CM.active = TRUE
        """
        cursor.execute(query)
        character_profiles = cursor.fetchall()
        print(f"character profiles : {character_profiles}")
        for cp in character_profiles:
            cp["basic_info"] = "\n".join([cp["mission_info"], cp["basic_info"]])
            del cp["mission_info"]
            if cp["character_id"] == character_uuid:
                character_profile = cp
            else:
                character_profile_other = cp

        query = f"""
        SELECT
            A.*,
            B.notification,
            C.`connection_id`
        FROM
            `user` AS A,
            `chatroom_member` AS B,
            `mission_game_chat_connection` AS C
        WHERE
            B.`game_chat_id` = {game_chat_id}
            AND A.email = B.email
            AND B.`game_chat_id` = C.`game_chat_id`
            AND A.email = C.email
            AND B.email IS NOT NULL
            AND B.active = TRUE
        """
        cursor.execute(query)
        user_profile = cursor.fetchone()

        query = """
        SELECT
            type,
            type AS name,
            1 AS duration,
            Eyelash_Mesh,
            Eyes_Mesh,
            Teeth_Mesh,
            Tongue_Mesh,
            EyeAO_Mesh,
            Head_Mesh
        FROM
            `avatar_expression_face`
        """
        cursor.execute(query)
        expression_keys.append(cursor.fetchall())

        # 캐릭터 id dict 생성
        name_dict = {
            user_profile["email"]: user_profile["nickname"],
            character_profile["character_id"]: character_profile["name"],
        }

        # 채팅 정보 가져오기
        chat_table_name = "idolmaster_game_chat"
        chat_tb = dynamodb.get_resource_obj(chat_table_name)
        chat_histories = chat_tb.query(
            KeyConditionExpression=Key("chat_id").eq(game_chat_id),
            ScanIndexForward=False,
            Limit=120,
        )["Items"]
        print("chat_histories : ", chat_histories)

        # API send 생성
        list_content = llm_api.content_merge_game_chat(
            character_profile,
            character_profile_other,
            chat_histories,
            user_profile,
            os.environ["API_ALIAS"],
        )

        # OpenAI API 생성 & 답변 추출
        answer, analysis_emotion = llm_api.call_llm_game_chat(
            list_content,
            character_profile["options"],
            os.environ["API_ALIAS"],
            safe_chat,
        )
        answer = (
            answer
            if f'{name_dict[character_profile["character_id"]]} : ' not in answer
            else answer.replace(
                f'{name_dict[character_profile["character_id"]]} : ', ""
            )
        )
        print(f"answer: {answer}")
        print(f"analysis_emotion: {analysis_emotion}")

        # 채팅 DB에 답변 저장
        timestamp_at = str(round(Decimal(time.timestampnow()), 5))

        answer_item = {
            "chat_id": game_chat_id,
            "send_time": timestamp_at,
            "id": character_profile["character_id"],
            "msg": answer,
        }
        dynamodb.put_item(chat_table_name, answer_item)

        # 최신 채팅시각 저장 & 캐릭터 사용 횟수 업데이트
        cursor.execute(
            "UPDATE `chatroom_member` SET `last_send_time` = %s WHERE `game_chat_id` = %s AND `character_id` = %s ",
            (timestamp_at, game_chat_id, character_profile["character_id"]),
        )
        cursor.execute(
            "UPDATE `character` SET total_usage_count = total_usage_count+1 WHERE `character_id` = %s",
            (character_profile["character_id"],),
        )
        db_connection.commit()

        # Emotion shapekey 포함
        emotions = []
        if os.environ["API_ALIAS"] == const.ALIAS_DEV:
            for expression_key in expression_keys[0]:
                print(expression_key)
                if expression_key["type"] == analysis_emotion:
                    # del expression_key['type']
                    temp_map = {}
                    data_map = {}
                    for k, v in expression_key.items():
                        if (
                            v is not None
                            and k != "type"
                            and k != "name"
                            and k != "duration"
                        ):
                            temp_map[k] = json.loads(v)
                        elif k == "type" or k == "name" or k == "duration":
                            data_map[k] = v
                        else:
                            temp_map[k] = v
                    data_map["value"] = temp_map
                    emotions.append(data_map)
            if len(emotions) > 0:
                answer_item["expression"] = random.choice(emotions)
            else:
                answer_item["expression"] = None
        else:
            shapekey_tb = dynamodb.get_resource_obj(
                "idolmaster_expression_shapekey", alias_pre=False
            )
            response = shapekey_tb.scan()
            items = response["Items"]
            for item in items:
                if item["type"] == analysis_emotion:
                    print(f"item: {item}")
                    emotions.append(item)
            if len(emotions) > 0:
                answer_item["expression"] = random.choice(emotions)
                answer_item["expression"]["value"] = json.loads(
                    answer_item["expression"]["value"]
                )
            else:
                answer_item["expression"] = None
            print("answer_item expression", answer_item["expression"])

        # Emotion file path
        motion_path = avatar_module.get_emotion_retargeting(
            analysis_emotion,
            character_profile["avatar_file_path"],
            character_profile["gender"],
        )
        answer_item["motion_url"] = "/" + motion_path
        print("motion file path :", answer_item["motion_url"])

        # # Motion 포함
        # answer_item["motion_url"] = None
        # character_file_name = character_profile["avatar_file_path"].split('/')[1].replace('.glb','').replace('.gltf','')
        # print(character_file_name)
        # motion_data = client.s3_client.list_objects_v2(
        #     Bucket=const.S3_BUCKET_NAME[os.environ['AWS_REGION']][os.environ['API_ALIAS']],
        #     Prefix='motion/'+character_file_name+'/'+analysis_emotion)
        # print(motion_data)
        # if 'Contents' in motion_data:
        #     motion_files = [file['Key'] for file in motion_data['Contents'] if not file['Key'].endswith('/')]
        #     if motion_files:
        #         file_path = random.choice(motion_files)
        #         answer_item["motion_url"] = gets3file(file_path, 7200, False)
        #         print(answer_item["motion_url"])

        # 채팅방에 전송
        answer_item["game_chat_id"] = answer_item["chat_id"]
        del answer_item["chat_id"]
        try:
            apigatewaymanagementapi.post_to_connection(
                ConnectionId=user_profile["connection_id"],
                Data=json.dumps(answer_item),
            )
        except apigatewaymanagementapi.exceptions.GoneException:
            print("Connection is gone.")
        except Exception:
            print(
                " ====== (websocket-groupsendAI) ERROR: {} ======".format(
                    traceback.format_exc()
                )
            )


def send_message_groupchat(
    connection_id: str,
    domain_name: str,
    email: str,
    groupchat_id: str,
    message: str,
    chat_id: str,
    chat_save: bool,
    character_uuid: str,
):
    utc_now_iso = time.now().isoformat() + "Z"
    timestamp_at = str(round(Decimal(time.timestampnow()), 5))
    db_connection = get_db_connection()

    # 웹소켓 연결
    endpoint_url = "https://" + domain_name + "/" + os.environ["API_ALIAS"]
    apigatewaymanagementapi = client.apigatewaymanagementapi_client(endpoint_url)

    # check dart
    check_dart = product_module.decrease_product(
        email, const.PRODUCT_CHARGE_TYPE_DEDUCT_MESSAGE
    )
    if not check_dart["result"]:
        # 캐릭터 조회
        db_connection = get_db_connection()
        with db_connection.cursor() as cursor:
            cursor.execute(
                """
            SELECT charact.*, persona.first_message, persona.basic_info, 'llama3-70b-instruct' as llm_type, ava.avatar_file_path, char_llm.main_prompt, '80' as top_k, '0.95' as temperature, char_llm.options
            FROM `character` AS charact, `character_persona` AS persona, `avatar` AS ava, `character_llm` AS char_llm
            WHERE charact.`character_id` IN (SELECT member_id FROM `groupchat_member` WHERE groupchat_id = %s AND is_user = FALSE AND active = TRUE)
                AND persona.`character_id` = charact.`character_id` AND charact.avatar_id = ava.avatar_id
            """,
                (groupchat_id,),
            )
            character_profiles = cursor.fetchall()

        # 캐릭터 별로 채팅 작성
        # 캐릭터 Random 선택
        character_cases = []
        if character_uuid:
            for character_profile in character_profiles:
                if character_profile["character_id"] == character_uuid:
                    character_cases.append(character_profile)
        else:
            ri = random.randint(1, len(character_profiles))
            character_cases = random.sample(character_profiles, ri)
            print("select count : ", ri)

        # 메세지 전송
        for character_profile in character_cases:
            apigatewaymanagementapi.post_to_connection(
                ConnectionId=connection_id,
                Data=json.dumps(
                    {
                        "status_code": 2,
                        "groupchat_uuid": groupchat_id,
                        "send_time": utc_now_iso,
                        "id": character_profile["character_id"],
                        "msg": "Not enough darts to proceed.",
                        "dart": check_dart["remain"]["dart"],
                    }
                ),
            )

        print("No dart")
        return False

    if chat_save:
        # 채팅내역 저장
        print("message before : ", message)
        message = message.replace("\xa0", " ")
        print("message after : ", message)
        insert_chat = {
            "groupchat_uuid": groupchat_id,
            "send_time": timestamp_at,
            "id": email,
            "msg": message,
        }
        dynamodb.put_item("idolmaster_groupchat", insert_chat)

    # 최신 채팅시각 업데이트
    with db_connection.cursor() as cursor:
        sql = "UPDATE `groupchat_member` SET `last_send_time` = %s WHERE `groupchat_id` = %s AND member_id = %s"
        cursor.execute(sql, (timestamp_at, groupchat_id, email))
    db_connection.commit()

    # 데이터 선언
    data_json = {
        "msg": message,
        "id": email,
        "send_time": utc_now_iso,
        "chat_id": chat_id,
        "dart": check_dart["remain"]["dart"],
    }

    # 채팅방에 전송
    with db_connection.cursor() as cursor:
        # 모든 커넥션 + 나를 차단한 사용자 제외
        sql = """
        SELECT email, connection_id
        FROM `groupchat_connection`
        WHERE groupchat_id = %s
        AND email NOT IN (SELECT email FROM `groupchat_block` WHERE blocked_email = %s )
        """
        cursor.execute(sql, (groupchat_id, email))
        connections = cursor.fetchall()

        print(f"모든 커넥션 + 나를 차단한 사용자 : {connections}")

        for con in connections:
            try:
                apigatewaymanagementapi.post_to_connection(
                    ConnectionId=con["connection_id"],
                    Data=json.dumps(data_json),
                )
            except apigatewaymanagementapi.exceptions.GoneException:
                print("Connection is gone.")
            except Exception:
                print(
                    " ====== ‼️ groupsend ERROR: {} ======".format(
                        traceback.format_exc()
                    )
                )

        # 사용자가 채팅방 접속해있지 않을 경우 푸시알림
        sql = """
        SELECT A.*, B.`connection_id`, C.fcm_token, (SELECT nickname FROM `user` WHERE email = %s) AS nickname
        FROM `groupchat_member` as A, `groupchat_connection` as B, `user` AS C
        WHERE A.groupchat_id = %s AND A.groupchat_id = B.groupchat_id AND A.member_id = B.email AND C.email = A.member_id AND A.member_id != %s AND A.active = TRUE AND A.is_user = TRUE AND A.notification = TRUE
        """
        cursor.execute(sql, (email, groupchat_id, email))
        groupchat_member = cursor.fetchall()
        for user in groupchat_member:
            endpoint_url = "https://" + domain_name + "/" + os.environ["API_ALIAS"]
            is_alive = check_connection(user["connection_id"], endpoint_url)
            if is_alive is False:
                if user["fcm_token"] and user["nickname"]:
                    send_push(
                        user["fcm_token"],
                        user["nickname"],
                        message,
                        "group/" + groupchat_id,
                    )

    db_connection.close()
    return True


def send_message_groupchat_ai(
    domain_name: str,
    email: str,
    groupchat_id: str,
    character_uuid: str,
    safe_chat: bool,
):
    # 캐릭터 & 유저 정보 & 삭제된 캐릭터 가져오기
    character_profiles = []
    user_profiles = []
    deleted_characters = []
    expression_keys = []
    db_connection = get_db_connection()
    with db_connection.cursor() as cursor:

        # TODO check query
        cursor.execute(
            """
        SELECT charact.*, persona.first_message, persona.basic_info, 'llama3-70b-instruct' as llm_type, ava.avatar_file_path, ava.gender, char_llm.main_prompt, '80' as top_k, '0.95' as temperature, char_llm.options
        FROM `character` AS charact, `character_persona` AS persona, `avatar` AS ava, `character_llm` AS char_llm
        WHERE charact.`character_id` IN (SELECT member_id FROM `groupchat_member` WHERE groupchat_id = %s AND is_user = FALSE AND active = TRUE)
            AND persona.`character_id` = charact.`character_id` AND charact.avatar_id = ava.avatar_id
        """,
            (groupchat_id,),
        )
        character_profiles = cursor.fetchall()

        cursor.execute(
            """
        SELECT A.*, B.notification, C.`connection_id`
        FROM `user` AS A, `groupchat_member` AS B, `groupchat_connection` AS C
        WHERE B.`groupchat_id` = %s AND A.email = B.member_id AND B.`groupchat_id` = C.`groupchat_id` AND A.email = C.email AND B.is_user = TRUE AND B.active = TRUE
        """,
            (groupchat_id,),
        )
        user_profiles = cursor.fetchall()
        cursor.execute(
            "SELECT member_id as id FROM `groupchat_member` WHERE `groupchat_id` = %s AND active = FALSE",
            (groupchat_id,),
        )
        deleted_characters = cursor.fetchall()
        cursor.execute(
            "SELECT type, type AS name, 1 AS duration, Eyelash_Mesh, Eyes_Mesh, Teeth_Mesh, Tongue_Mesh, EyeAO_Mesh, Head_Mesh FROM `avatar_expression_face`"
        )
        expression_keys.append(cursor.fetchall())

    # 캐릭터 id dict 생성
    name_dict = {}
    for character in character_profiles:
        name_dict[character["character_id"]] = character["name"]
    for user in user_profiles:
        name_dict[user["email"]] = user["nickname"]

    # 캐릭터 별로 채팅 작성
    # 캐릭터 Random 선택
    character_cases = []
    if character_uuid:
        for character_profile in character_profiles:
            if character_profile["character_id"] == character_uuid:
                character_cases.append(character_profile)
    else:
        ri = random.randint(1, len(character_profiles))
        character_cases = random.sample(character_profiles, ri)
        print("select count : ", ri)

    # 채팅 정보 가져오기
    chat_table_name = "idolmaster_groupchat"
    chat_tb = dynamodb.get_resource_obj(chat_table_name)
    chat_histories = chat_tb.query(
        KeyConditionExpression=Key("groupchat_uuid").eq(groupchat_id),
        ScanIndexForward=False,
        Limit=120,
    )["Items"]
    print("chat_histories : ", chat_histories)

    for character_profile in character_cases[:1]:
        print("select character : ", character_profile["name"])

        # 사용되는 캐릭터 제외 나머지 캐릭터 리스트
        # 중복 제거를 위해 딕셔너리를 사용하여 캐릭터 ID를 키로 사용
        other_character_dict = {}
        for character in character_profiles:
            # 자기 자신은 제외
            if character["character_id"] != character_profile["character_id"]:
                other_character_dict[character["character_id"]] = character

        # 딕셔너리의 값들을 리스트로 변환
        other_character_profiles = list(other_character_dict.values())

        # API send 생성
        list_content = llm_api.content_merge_groupchat(
            character_profile,
            other_character_profiles,
            user_profiles,
            chat_histories,
            deleted_characters,
            name_dict,
            os.environ["API_ALIAS"],
        )

        # OpenAI API 생성 & 답변 추출
        # print(list_content)
        answer, analysis_emotion, block_reason = llm_api.call_llm_groupchat(
            "gpt-4o",
            list_content,
            "",
            character_profile["llm_type"],
            character_profile["top_k"],
            character_profile["temperature"],
            character_profile["options"],
            os.environ["API_ALIAS"],
            safe_chat,
        )
        answer = (
            answer
            if f'{name_dict[character_profile["character_id"]]} : ' not in answer
            else answer.replace(
                f'{name_dict[character_profile["character_id"]]} : ', ""
            )
        )
        print(f"answer: {answer}")
        print(f"analysis_emotion: {analysis_emotion}")
        print(f"block_reason: {block_reason}")

        # 채팅 DB에 답변 저장
        timestamp_at = str(round(Decimal(time.timestampnow()), 5))

        answer_item = {
            "groupchat_uuid": groupchat_id,
            "send_time": timestamp_at,
            "id": character_profile["character_id"],
            "msg": answer,
        }
        dynamodb.put_item(chat_table_name, answer_item)

        # 최신 채팅시각 저장 & 캐릭터 사용 횟수 업데이트
        with db_connection.cursor() as cursor:
            cursor.execute(
                "UPDATE `groupchat_member` SET `last_send_time` = %s WHERE `groupchat_id` = %s AND `member_id` = %s ",
                (timestamp_at, groupchat_id, character_profile["character_id"]),
            )
            cursor.execute(
                "UPDATE `character` SET total_usage_count = total_usage_count+1 WHERE `character_id` = %s",
                (character_profile["character_id"],),
            )
        db_connection.commit()

        # 채팅방에 답변 전송
        url = "https://" + domain_name + "/" + os.environ["API_ALIAS"]
        apigatewaymanagementapi = client.apigatewaymanagementapi_client(url)

        # Emotion shapekey 포함
        emotions = []
        if os.environ["API_ALIAS"] == const.ALIAS_DEV:
            for expression_key in expression_keys[0]:
                print(expression_key)
                if expression_key["type"] == analysis_emotion:
                    # del expression_key['type']
                    temp_map = {}
                    data_map = {}
                    for k, v in expression_key.items():
                        if (
                            v is not None
                            and k != "type"
                            and k != "name"
                            and k != "duration"
                        ):
                            temp_map[k] = json.loads(v)
                        elif k == "type" or k == "name" or k == "duration":
                            data_map[k] = v
                        else:
                            temp_map[k] = v
                    data_map["value"] = temp_map
                    emotions.append(data_map)
            if len(emotions) > 0:
                answer_item["expression"] = random.choice(emotions)
            else:
                answer_item["expression"] = None
        else:
            shapekey_tb = dynamodb.get_resource_obj(
                "idolmaster_expression_shapekey", alias_pre=False
            )
            response = shapekey_tb.scan()
            items = response["Items"]
            for item in items:
                if item["type"] == analysis_emotion:
                    print(f"item: {item}")
                    emotions.append(item)
            if len(emotions) > 0:
                answer_item["expression"] = random.choice(emotions)
                answer_item["expression"]["value"] = json.loads(
                    answer_item["expression"]["value"]
                )
            else:
                answer_item["expression"] = None
            print("answer_item expression", answer_item["expression"])

        # Emotion file path
        motion_path = avatar_module.get_emotion_retargeting(
            analysis_emotion,
            character_profile["avatar_file_path"],
            character_profile["gender"],
        )
        answer_item["motion_url"] = "/" + motion_path
        print("motion file path :", answer_item["motion_url"])

        # # Motion 포함
        # answer_item["motion_url"] = None
        # character_file_name = character_profile["avatar_file_path"].split('/')[1].replace('.glb','').replace('.gltf','')
        # print(character_file_name)
        # motion_data = client.s3_client.list_objects_v2(
        #     Bucket=const.S3_BUCKET_NAME[os.environ['AWS_REGION']][os.environ['API_ALIAS']],
        #     Prefix='motion/'+character_file_name+'/'+analysis_emotion)
        # print(motion_data)
        # if 'Contents' in motion_data:
        #     motion_files = [file['Key'] for file in motion_data['Contents'] if not file['Key'].endswith('/')]
        #     if motion_files:
        #         file_path = random.choice(motion_files)
        #         answer_item["motion_url"] = gets3file(file_path, 7200, False)
        #         print(answer_item["motion_url"])

        # 채팅방에 전송
        # 사용자가 차단한 캐릭터는 발송 X
        with db_connection.cursor() as cursor:
            for user_profile in user_profiles:
                user_email = user_profile["email"]
                creator_email = character_profile["email"]
                character_id = character_profile["character_id"]

                sql = """
                SELECT COUNT(*) as count FROM (
                    SELECT email, character_id FROM `character_block` WHERE email = %s AND character_id = %s
                    UNION
                    SELECT email, blocked_email FROM `user_block` WHERE email = %s AND blocked_email = %s
                ) AS block_check
                """
                cursor.execute(
                    sql, (user_email, character_id, user_email, creator_email)
                )
                result = cursor.fetchone()
                if result and result["count"] > 0:
                    print(
                        f"User {user_email} has blocked character {character_profile['character_id']} or its creator {creator_email}."
                    )
                    continue

                try:
                    apigatewaymanagementapi.post_to_connection(
                        ConnectionId=user_profile["connection_id"],
                        Data=json.dumps(answer_item),
                    )
                except apigatewaymanagementapi.exceptions.GoneException:
                    print("Connection is gone.")
                except Exception:
                    print(
                        " ====== (websocket-groupsendAI) ERROR: {} ======".format(
                            traceback.format_exc()
                        )
                    )

                # 사용자가 채팅방 접속해있지 않을 경우 푸시알림
                endpoint_url = "https://" + domain_name + "/" + os.environ["API_ALIAS"]
                is_alive = check_connection(user_profile["connection_id"], endpoint_url)
                if is_alive is False and user_profile["fcm_token"]:
                    send_push(
                        user_profile["fcm_token"],
                        character_profile["name"],
                        answer,
                        "group/" + groupchat_id,
                    )

    db_connection.close()


def send_push(user_token, title, body, route):
    url = "https://fcm.googleapis.com/v1/projects/idolmaster-4413b/messages:send"
    access_token = get_access_token()
    headers = {
        "Content-Type": "application/json; UTF-8",
        "Authorization": "Bearer " + access_token,
    }

    data = {
        "message": {
            "token": user_token,
            "notification": {"title": title, "body": body},
            "data": {
                "click_action": "FLUTTER_NOTIFICATION_CLICK",
                "type": "push",
                "value": route,
            },
            "android": {
                "notification": {
                    "body": body,
                },
                "priority": "high",
                "direct_boot_ok": True,
            },
            "apns": {
                "headers": {"apns-push-type": "alert", "apns-priority": "10"},
                "payload": {
                    "aps": {
                        "alert": {"title": title, "body": body},
                        "sound": "default",
                        "badge": 1,
                        "content_available": 1,
                    },
                },
            },
        }
    }

    response = http_request.request("POST", url, headers=headers, data=data)
    if response["status_code"] != 200:
        print(f"Error: {response['status_code']}, {response['response']}")
    else:
        print(f"FCM response: {response['response']}")
