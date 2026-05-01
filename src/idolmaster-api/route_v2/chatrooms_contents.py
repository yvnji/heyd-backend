from lib.decorator import mandatory_params
from lib.exception import (IdolmasterBadRequestException,
                           IdolmasterForbiddenException,
                           IdolmasterResourceNotFoundExeption)
from service import character as character_module
from service import chatroom as chatroom_module
from service import content as content_module


@mandatory_params([
    "title", "background_name", "background_id", "character_ids"])
def post_chatrooms_contents(event, context, body):
    """컨텐츠에 들어갈 채팅방 생성"""
    user_id = int(event["requestContext"]["authorizer"]["db_id"])
    title = body["title"]
    background_name = body["background_name"]
    background_id = body["background_id"]
    bgm_id = body.get("bgm_id")
    character_ids = body["character_ids"].replace(" ", "").split(",")

    # check body
    try:
        assert len(title) <= 50
    except AssertionError:
        raise IdolmasterBadRequestException(message="Invalid params", result_code=1)

    # check file_path
    if not content_module.get_background(background_id):
        raise IdolmasterResourceNotFoundExeption(message="background_id not found")
    background_id = int(background_id)
    if bgm_id:
        if not content_module.get_bgm(bgm_id):
            raise IdolmasterResourceNotFoundExeption(message="bgm_id not found", result_code=1)
        bgm_id = int(bgm_id)

    # 캐릭터 ID 확인
    for cid in character_ids:
        if not character_module.get_character(cid):
            raise IdolmasterResourceNotFoundExeption(message="character_ids not found", result_code=2)

    chatroom_id = chatroom_module.create_chatroom(
        title,
        character_ids,
        user_id,
        background_name,
        background_id,
        bgm_id)

    return {"data": {"chatroom_id": chatroom_id}}


@mandatory_params([
    "chatrooms_contents", "title", "background_name", "background_id", "character_ids"])
def put_chatrooms_contents(event, context, body):
    """컨텐츠에 들어갈 채팅방 수정"""
    user_id = int(event["requestContext"]["authorizer"]["db_id"])
    chatroom_id = body["chatrooms_contents"]
    title = body["title"]
    background_name = body["background_name"]
    background_id = body["background_id"]
    character_ids = body["character_ids"].replace(" ", "").split(",")
    bgm_id = body.get("bgm_id")

    # check body
    try:
        assert len(title) <= 50
    except AssertionError:
        raise IdolmasterBadRequestException(message="Invalid params", result_code=1)

    # check chatroom_id
    chatroom_item = chatroom_module.get_chatroom(chatroom_id)
    if not chatroom_item:
        raise IdolmasterResourceNotFoundExeption(message="chatroom_id not found")
    chatroom_id = int(chatroom_id)

    # check authorization
    if chatroom_item["creator_id"] != user_id:
        raise IdolmasterForbiddenException

    # check file_path
    if not content_module.get_background(background_id):
        raise IdolmasterResourceNotFoundExeption(message="background_id not found", result_code=1)
    background_id = int(background_id)
    if bgm_id:
        if not content_module.get_bgm(bgm_id):
            raise IdolmasterResourceNotFoundExeption(message="bgm_id not found", result_code=2)
        bgm_id = int(bgm_id)

    # 캐릭터 ID 확인
    for cid in character_ids:
        if not character_module.get_character(cid):
            raise IdolmasterResourceNotFoundExeption(message="character_ids not found", result_code=3)

    chatroom_module.update_chatroom(
        chatroom_id,
        title,
        character_ids,
        background_name,
        background_id,
        bgm_id)
