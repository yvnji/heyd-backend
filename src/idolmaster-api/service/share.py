import hashlib
import random
from datetime import datetime

import shortuuid
from boto3.dynamodb.conditions import Key

import const
from lib import time
from lib.decorator import preprocessing_cursor
from thirdparty import dynamodb


@preprocessing_cursor
def create_shared_chatroom_guest(shared_chatroom_id: str, guest_id: str, cursor: object = None) -> dict:
    """공유된 채팅방 게스트 생성

    :param shared_chatroom_id: 공유된 채팅방 ID
    :param guest_id: 게스트 ID
    :param cursor: pymysql.connect().cursor()

    :return: 게스트 정보
    """
    query = """
    INSERT INTO `content_chatroom_shared_guest` (id, shared_chatroom_id)
    VALUES (%s, %s)
    """
    cursor.execute(query, (guest_id, shared_chatroom_id))


@preprocessing_cursor
def get_shared_chatroom(shared_chatroom_id: str, cursor: object = None) -> dict:
    """공유된 채팅방 조회

    :param shared_chatroom_id: 공유된 채팅방 ID
    :param cursor: pymysql.connect().cursor()

    :return: 공유된 채팅방 정보
        {
            "id": str,
            "created_at": datetime.datetime,
            "chatroom_activated_id": int,
            "nickname": str,
            "gender": str,
            "birth_date": datetime.date,
            "usage_count": int,
            "chatroom_id": int,
            "start_at": datetime.datetime,
            "character_ids": [str, str, ...]
        }
    """
    query = """
    SELECT
        CCS.id,
        CCS.created_at,
        CCS.chatroom_activated_id,
        CCS.nickname,
        CCS.gender,
        CCS.birth_date,
        CCS.usage_count,
        CC.chatroom_id,
        CCA.start_at,
        GROUP_CONCAT(CCC.character_id SEPARATOR ',') AS character_ids
    FROM `content_chatroom_shared` AS CCS
    JOIN `content_chatroom_active` AS CCA ON CCS.chatroom_activated_id = CCA.id
    JOIN `content_connect` AS CC ON CC.id = CCA.connect_id
    LEFT JOIN `content_chatroom_character` AS CCC ON CCC.chatroom_id = CC.chatroom_id
    WHERE CCS.id = %s
    GROUP BY CCC.chatroom_id
    """
    cursor.execute(query, (shared_chatroom_id))
    item = cursor.fetchone()
    if item:
        item["character_ids"] = item["character_ids"].split(",")
    return item


@preprocessing_cursor
def get_shared_chatroom_guest(shared_chatroom_id: str, guest_id: str, cursor: object = None) -> dict:
    """공유된 채팅방 게스트 조회

    :param shared_chatroom_id: 공유된 채팅방 ID
    :param guest_id: 게스트 ID
    :param cursor: pymysql.connect().cursor()

    :return: 게스트 정보
        {
            "guest_id": str,
            "usage_count": int
        }
    """
    query = """
    SELECT
        id AS guest_id,
        usage_count
    FROM `content_chatroom_shared_guest`
    WHERE shared_chatroom_id = %s AND id = %s
    """
    cursor.execute(query, (shared_chatroom_id, guest_id))
    item = cursor.fetchone()
    return item if item else {}


@preprocessing_cursor
def list_shared_chatroom_chats(
    shared_chatroom_id: str,
    character_ids: list,
    chatroom_activated_id: int,
    created_at: datetime,
    start_at: datetime,
    cursor: object = None
) -> list:
    """공유된 채팅방 채팅 이력 조회

    :param shared_chatroom_id: 공유된 채팅방 ID
    :param character_ids: 채팅방 캐릭터 ID 리스트
    :param chatroom_activated_id: 공유 전 활성화 채팅방 ID
    :param created_at: 공유된 채팅방 생성 시간
    :param start_at: 공유 전 활성화 채팅방 시작 시간
    :param cursor: pymysql.connect().cursor()

    :return: 공유된 채팅방 채팅 이력
        [
            {
                "timestamp_at": Decimal,
                "chat": str,
                "character_id": str,
                "character_name": str,
                "user_nickname": str,   # 사용자 닉네임 (공유 전 사용자 채팅일 경우 존재)
                "guest_nickname": str,   # 게스트 닉네임 (공유 후 게스트 채팅일 경우 존재)
            },
            ...
        ]
    """

    # 공유 전 채팅방 채팅 이력 조회
    origin_table_name = "idolmaster_content_chat"
    last_evaluated_key = None
    chats_ret = []
    origin_chats = []
    origin_from = time.totimestamp(start_at)
    origin_to = time.totimestamp(created_at)

    while True:
        items, last_evaluated_key = dynamodb.fetch_data_query(
            origin_table_name,
            Key("chatroom_activated_id").eq(chatroom_activated_id) & Key("timestamp_at").between(origin_from, origin_to),
            index_name="chatroom_activated_id-timestamp_at-index",
            limit=500,
            index_forward=False,
            last_evaluated_key=last_evaluated_key,
        )
        origin_chats.extend(items)
        if not last_evaluated_key:
            break

    # 기존 사용자 nickname 조회
    user_ids = list(set([str(chat.get("user_id")) for chat in origin_chats]))
    if 'None' in user_ids:
        user_ids.remove('None')

    if user_ids:
        user_ids_str = ", ".join(user_ids)
        query = f"""
        SELECT
            id,
            nickname
        FROM `user`
        WHERE id IN ({user_ids_str})
        """
        cursor.execute(query)
        user_nicknames = cursor.fetchall()
    else:
        user_nicknames = []

    user_nicknames_dict = {user["id"]: user["nickname"] for user in user_nicknames}

    for chat in origin_chats:
        item = {
            "timestamp_at": chat["timestamp_at"],
            "chat": chat["chat"],
            "character_id": chat["character_id"],
        }
        if chat.get("user_id"):
            item["user_nickname"] = user_nicknames_dict[chat["user_id"]]
        chats_ret.append(item)

    # 공유 후 채팅방 채팅 이력 조회 -> 이력은 조회 x, LLM 입력 x
    # table_name = "idolmaster_content_chat_shared"
    # chat_table = dynamodb.get_resource_obj(table_name)
    # last_evaluated_key = None
    # while True:
    #     items, last_evaluated_key = dynamodb.fetch_data_query(
    #         table_name,
    #         Key("shared_chatroom_id").eq(shared_chatroom_id),
    #         projection_exp="timestamp_at, chat, character_id, guest_nickname",
    #         limit=500,
    #         index_forward=False,
    #         last_evaluated_key=last_evaluated_key,
    #     )
    #     chats_ret = items + chats_ret
    #     if not last_evaluated_key:
    #         break

    # 채팅방 캐릭터 이름 조회
    query = f"""
    SELECT
        character_id,
        name
    FROM `character`
    WHERE character_id IN ('{"', '".join(character_ids)}')
    """
    cursor.execute(query)
    character_names_dict = {character["character_id"]: character["name"] for character in cursor.fetchall()}
    for chat in chats_ret:
        chat["character_name"] = character_names_dict[chat["character_id"]]

    return chats_ret


@preprocessing_cursor
def share_chatroom(
    chatroom_activated_id: int,
    nickname: str = None,
    gender: str = None,
    birth_date: str = None,
    cursor: object = None
) -> str:
    """공유할 컨텐츠 채팅방 생성

    :param chatroom_activated_id: 활성화된 채팅방 ID
    :param nickname: 게스트 닉네임
    :param gender: 게스트 성별
    :param birth_date: 게스트 생년월일
    :param cursor: pymysql.connect().cursor()

    :return: 생성된 채팅방 공유 ID
    """
    share_id = shortuuid.uuid()

    # 게스트 기본 정보
    if not nickname:
        nickname = f"guest_{random.randint(100000, 999999)}"
    if not gender:
        gender = "M"
    if not birth_date:
        birth_date = "2000-01-01"

    query = """
    INSERT INTO `content_chatroom_shared` (id, chatroom_activated_id, nickname, gender, birth_date)
    VALUES (%s, %s, %s, %s, %s)
    """
    cursor.execute(query, (share_id, chatroom_activated_id, nickname, gender, birth_date))

    return share_id


def verify_guest_id(guest_id: str, hash_key: str) -> bool:
    """게스트 ID 검증

    :param guest_id: 게스트 ID
    :param hash_key: 검증을 위한 해시 키 (공유된 salt + 게스트 ID)

    :return: 검증 결과
    """
    hash_obj = hashlib.sha256()
    hash_obj.update((const.SHARED_CHATROOM_SALT + guest_id).encode("utf-8"))
    return hash_obj.hexdigest() == hash_key
