from datetime import datetime

from lib.decorator import mandatory_params
from lib.exception import (IdolmasterBadRequestException,
                           IdolmasterResourceNotFoundExeption)
from service import chatroom as chatroom_module
from service import share as share_module


@mandatory_params(["chatroom_id"])
def post_shares_chatrooms(event, context, body):
    """채팅방 공유"""
    user_id = int(event["requestContext"]["authorizer"]["db_id"])
    chatroom_id = body["chatroom_id"]
    birth_date = body.get("birth_date")
    nickname = body.get("nickname")
    gender = body.get("gender")

    try:
        if birth_date:
            birth_date = datetime.strptime(birth_date, "%m%d%Y").strftime("%Y-%m-%d")
        if gender:
            assert gender in ["M", "F"]
        if nickname:
            assert len(nickname) <= 20
    except (AssertionError, ValueError):
        raise IdolmasterBadRequestException(message="Invalid params", result_code=1)

    # check chatroom_id
    chatroom_item = chatroom_module.get_chatroom(chatroom_id)
    if not chatroom_item:
        raise IdolmasterResourceNotFoundExeption(message="chatroom_id not found")
    chatroom_id = int(chatroom_id)

    # check chatroom_activated_id
    chatroom_activated_item = chatroom_module.get_chatroom_activated(user_id, chatroom_id=chatroom_id)
    if not chatroom_activated_item:
        raise IdolmasterBadRequestException(message="chatroom_id is not activated", result_code=2)
    chatroom_activated_id = int(chatroom_activated_item["id"])

    # 공유방 생성
    shared_chatroom_id = share_module.share_chatroom(
        chatroom_activated_id,
        nickname,
        gender,
        birth_date)

    return {"data": {"shared_chatroom_id": shared_chatroom_id}}
