import const
from lib.decorator import mandatory_params
from lib.exception import (IdolmasterBadRequestException,
                           IdolmasterConflictResourceException,
                           IdolmasterForbiddenException,
                           IdolmasterResourceNotFoundExeption)
from service import chatroom as chatroom_module
from service import share as share_module
from service import product as product_module


@mandatory_params(["shares_chatrooms", "guest_id"])
def get_shares_chatrooms(event, context, params):
    """공유된 채팅방 조회"""
    shared_chatroom_id = params["shares_chatrooms"]
    guest_id = params["guest_id"]
    ret = {}

    # guest_id 검증
    guest_item = share_module.get_shared_chatroom_guest(shared_chatroom_id, guest_id)
    if not guest_item:
        raise IdolmasterForbiddenException(message="Forbidden shared_chatroom_id or guest_id", result_code=1)

    # 공유 채팅방 조회
    shared_chatroom = share_module.get_shared_chatroom(shared_chatroom_id)

    # 연결된 채팅방 데이터 조회
    if shared_chatroom:
        ret = chatroom_module.get_chatroom_details(shared_chatroom["chatroom_id"])

        # 사용 횟수 확인 (daily reward 만큼)
        products = product_module.list_charge_type(const.PRODUCT_CHARGE_TYPE_REWARD_DAILY)
        total_count = products[0]["dart"]
        remained_count = total_count - guest_item["usage_count"]
        ret["remained_count"] = remained_count if remained_count > 0 else 0

    return {"data": ret}


@mandatory_params(["shares_chatrooms", "guest_id"])
def get_shares_chatrooms_chats(event, context, params):
    """공유된 채팅방 채팅 이력 조회"""
    shared_chatroom_id = params["shares_chatrooms"]
    guest_id = params["guest_id"]
    chats = []

    # guest_id 검증
    guest_item = share_module.get_shared_chatroom_guest(shared_chatroom_id, guest_id)
    if not guest_item:
        raise IdolmasterForbiddenException(message="Forbidden shared_chatroom_id or guest_id", result_code=1)

    # 공유 채팅방 조회
    shared_chatroom = share_module.get_shared_chatroom(shared_chatroom_id)

    # 공유 채팅방 채팅 이력 조회
    if shared_chatroom:
        res = share_module.list_shared_chatroom_chats(
            shared_chatroom_id,
            shared_chatroom["character_ids"],
            shared_chatroom["chatroom_activated_id"],
            shared_chatroom["created_at"],
            shared_chatroom["start_at"]
        )

        # receiver, sender 구분
        for r in res:
            item = {
                "timestamp_at": r["timestamp_at"],
                "chat": r["chat"],
                "receiver": {
                    "character_id": r["character_id"],
                    "nickname": r["character_name"]
                }
            }
            if r.get("user_nickname"):
                item["sender"] = {
                    "character_id": None,
                    "nickname": r["user_nickname"],
                    "type": 2
                }
            elif r.get("guest_nickname"):
                item["sender"] = {
                    "character_id": None,
                    "nickname": r["guest_nickname"],
                    "type": 3
                }
            else:
                item["receiver"] = None
                item["sender"] = {
                    "character_id": r["character_id"],
                    "nickname": r["character_name"],
                    "type": 1
                }
            chats.append(item)

    return {"data": chats}


@mandatory_params(["shares_chatrooms", "guest_id", "chat", "character_id"])
def post_shares_chatrooms_chats(event, context, body):
    """공유된 채팅방 채팅 보내기"""
    shared_chatroom_id = body["shares_chatrooms"]
    guest_id = body["guest_id"]
    chat = body["chat"]
    character_id = body["character_id"]
    block_reason = body.get("block_reason")

    # guest_id 검증
    guest_item = share_module.get_shared_chatroom_guest(shared_chatroom_id, guest_id)
    if not guest_item:
        raise IdolmasterForbiddenException(message="Forbidden shared_chatroom_id or guest_id", result_code=1)

    # check shared_chatroom_id
    shared_chatroom = share_module.get_shared_chatroom(shared_chatroom_id)
    if not shared_chatroom:
        raise IdolmasterResourceNotFoundExeption(message="shared_chatroom_id not found")

    # check character_id
    if character_id not in shared_chatroom["character_ids"]:
        raise IdolmasterResourceNotFoundExeption(message="character_id not found", result_code=1)
    shared_chatroom["character_ids"].remove(character_id)
    shared_chatroom["character_ids"] = [character_id] + shared_chatroom["character_ids"]

    # 사용 횟수 확인 (daily reward 만큼)
    products = product_module.list_charge_type(const.PRODUCT_CHARGE_TYPE_REWARD_DAILY)
    total_count = products[0]["dart"]
    remained_count = total_count - guest_item["usage_count"]
    if remained_count <= 0:
        raise IdolmasterBadRequestException(message="Use all chat counts", result_code=1)

    # 채팅 보내기
    ret = chatroom_module.send_chat(
        shared_chatroom["character_ids"],
        const.CHAT_TYPE_SHARE,
        chat,
        shared_chatroom_id=shared_chatroom_id,
        guest_id=guest_id,
        block_reason=block_reason
    )
    ret["remained_count"] = remained_count - 1

    return {"data": ret}


@mandatory_params(["shares_chatrooms", "guest_id", "hash_key"])
def post_shares_chatrooms_guests(event, context, body):
    """공유된 채팅방 게스트 추가"""
    shared_chatroom_id = body["shares_chatrooms"]
    guest_id = body["guest_id"]
    hash_key = body["hash_key"]

    # check shared_chatroom_id
    shared_chatroom = share_module.get_shared_chatroom(shared_chatroom_id)
    if not shared_chatroom:
        raise IdolmasterResourceNotFoundExeption(message="shared_chatroom_id not found")

    # guest_id 검증
    if not share_module.verify_guest_id(guest_id, hash_key):
        raise IdolmasterForbiddenException(message="Forbidden guest_id or hash_key", result_code=1)

    # guest_id 조회
    guest_item = share_module.get_shared_chatroom_guest(shared_chatroom_id, guest_id)
    if guest_item:
        raise IdolmasterConflictResourceException(message="Guest already exists in shared_chatroom_id")

    # 게스트 추가
    share_module.create_shared_chatroom_guest(shared_chatroom_id, guest_id)
