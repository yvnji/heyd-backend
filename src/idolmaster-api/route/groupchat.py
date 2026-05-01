import json

from lib.decorator import mandatory_params
from lib.exception import IdolmasterConflictResourceException
from lib.exception import IdolmasterForbiddenException
from lib.exception import IdolmasterResourceNotFoundExeption
from service import character as character_module
from service import groupchat as groupchat_module
from thirdparty.mariadb import get_db_connection


def delete_block_user(event, context, params):
    body = json.loads(event["body"])

    # groupchat_id 확인
    chat_members = groupchat_module.list_members(body["groupchat_id"])
    if not chat_members:
        raise IdolmasterResourceNotFoundExeption(message="groupchat_id not found")
    if body["email"] not in chat_members:
        raise IdolmasterForbiddenException
    if body["block_user_id"] not in chat_members:
        raise IdolmasterResourceNotFoundExeption(message="block_user_id not found in this groupchat")

    return groupchat_module.update_block_user(
        body["email"], body["groupchat_id"], body["block_user_id"], False
    )


@mandatory_params(["email"])
def post_get_groupchat_list(event, context, body):
    params = event["queryStringParameters"]
    params = params if params else {}
    email = body["email"]
    page = int(params.get("page", 1))
    page_size = int(params.get("page_size", 10))
    room_accessibility = params.get("type", "")
    search_keyword = params.get("search", "")
    offset = (page - 1) * page_size
    res = groupchat_module.list_groupchat(
        email, page_size, room_accessibility, search_keyword, offset
    )
    return {
        "result": 1,
        "total": res["total_count"],
        "data": res["chats"]
    }


@mandatory_params(["email", "groupchat_id", "block_user_id"])
def post_block_user(event, context, body):

    # groupchat_id 확인
    chat_members = groupchat_module.list_members(body["groupchat_id"])
    if not chat_members:
        raise IdolmasterResourceNotFoundExeption(message="groupchat_id not found")
    if body["email"] not in chat_members:
        raise IdolmasterForbiddenException
    if body["block_user_id"] not in chat_members:
        raise IdolmasterResourceNotFoundExeption(message="block_user_id not found in this groupchat")

    return groupchat_module.update_block_user(
        body["email"], body["groupchat_id"], body["block_user_id"], True
    )


@mandatory_params(["email", "chatroom_id"])
def post_check_member(event, context, body):
    res = groupchat_module.check_member(body["email"], body["chatroom_id"])
    return {
        "result": 1,
        "data": res
    }


@mandatory_params(
    [
        "email",
        "character_ids",
        "name",
        "description",
        "accessibility",
        "password",
        "max_participants_num",
        "language",
    ]
)
def post_create_chatroom(event, context, body):
    cursor = get_db_connection().cursor()

    # character_id 확인
    for character_id in body["character_ids"]:
        if not character_module.get_character(character_id, cursor=cursor):
            raise IdolmasterResourceNotFoundExeption(message="character_ids not found")

    groupchat_id = groupchat_module.create_chatroom(
        body["email"],
        body["character_ids"],
        body["name"],
        body["description"],
        body["accessibility"],
        body["password"],
        int(body["max_participants_num"]),
        body["language"],
    )
    return {
        "result": 1,
        "groupchat_id": groupchat_id
    }


@mandatory_params(["email", "chatroom_id", "accessibility"])
def post_enter_groupchat(event, context, body):
    ret = {
        "result": 0,
        "is_allowed": False
    }

    # groupchat_id 확인
    chat_members = groupchat_module.list_members(body["chatroom_id"])
    if not chat_members:
        raise IdolmasterResourceNotFoundExeption(message="chatroom_id not found")

    status_code = groupchat_module.enter_groupchat(
        body["email"], body["chatroom_id"], body["accessibility"], body.get("password")
    )

    if not status_code:
        ret["result"] = 1
        ret["is_allowed"] = True
    elif status_code == 1:
        ret["error_message"] = "There is no chatroom with the specified ID."
    elif status_code == 2:
        ret["error_message"] = "This chatroom has deleted."
    elif status_code == 3:
        ret["error_message"] = "The number of participants has exceeded the limit."
    elif status_code == 4:
        ret["error_message"] = "Password does not match."

    return ret


@mandatory_params(["email", "chatroom_id"])
def post_get_chatroom_info(event, context, body):
    # groupchat_id 확인
    chat_members = groupchat_module.list_members(body["chatroom_id"])
    if not chat_members:
        raise IdolmasterResourceNotFoundExeption(message="chatroom_id not found ")

    res = groupchat_module.get_chatroom_info(body["email"], body["chatroom_id"])
    return {
        "result": 1,
        "data": res
    }


@mandatory_params(["email", "groupchat_id", "last_evaluated_key"])
def post_get_previous_chat(event, context, body):
    # groupchat_id 확인
    chat_members = groupchat_module.list_members(body["groupchat_id"])
    if not chat_members:
        raise IdolmasterResourceNotFoundExeption(message="groupchat_id not found ")

    res = groupchat_module.get_previous_chat(
        body["email"], body["groupchat_id"], body["last_evaluated_key"]
    )
    return {
        "result": 1,
        "data": res["chats"],
        "last_evaluated_key": res["last_evaluated_key"]
    }


@mandatory_params(["email", "chatroom_id"])
def post_leave_chatroom(event, context, body):
    # groupchat_id 확인
    chat_members = groupchat_module.list_members(body["chatroom_id"])
    if not chat_members:
        raise IdolmasterResourceNotFoundExeption(message="chatroom_id not found")
    if body["email"] not in chat_members:
        raise IdolmasterConflictResourceException

    groupchat_module.leave_chatroom(body["email"], body["chatroom_id"])
    return {
        "result": 1,
        "chatroom_id": body["chatroom_id"]
    }
