import json

from lib.decorator import mandatory_params
from lib.exception import IdolmasterBadRequestException
from lib.exception import IdolmasterForbiddenException
from lib.exception import IdolmasterResourceNotFoundExeption
from service import character as character_module
from service import chat as chat_module
from service import groupchat as groupchat_module
from thirdparty.mariadb import get_db_connection


def delete_evaluate_chat(event, context, params):
    body = json.loads(event["body"])
    send_time, email = body["send_time#user_id"].split("#")
    room_id = body["chatroom_id"]
    cursor = get_db_connection().cursor()

    # chatroom_id 확인
    if (
        not chat_module.check_active(room_id, cursor=cursor)
        and not groupchat_module.check_active(room_id, cursor=cursor)
    ):
        raise IdolmasterResourceNotFoundExeption(message="chatroom_id not found")

    # chatroom_id에 대한 권한이 있는지 확인
    if (
        not chat_module.check_member(email, room_id, cursor=cursor)
        and not groupchat_module.check_member(email, room_id)
    ):
        raise IdolmasterForbiddenException

    chat_module.delete_evaluate_chat(email, room_id, send_time)
    return {"result": 1}


def delete_update_mystery_chat_step(event, context, params):
    params = json.loads(event["body"])
    email = params["email"]
    chatroom_id = params["chatroom_id"]
    current_step = params["step"]
    cursor = get_db_connection().cursor()

    # chatroom_id 확인
    if not chat_module.check_active(chatroom_id, cursor=cursor):
        raise IdolmasterResourceNotFoundExeption(message="chatroom_id not found")

    # chatroom_id에 대한 권한이 있는지 확인
    if not chat_module.check_member(email, chatroom_id, cursor=cursor):
        raise IdolmasterForbiddenException

    # step 확인
    if current_step not in ["Introduction", "Guessing", "Choices", "Conclusion", "GameOver"]:
        raise IdolmasterBadRequestException(message="Invalid step")

    chat_module.update_mystery_chat_step(email, chatroom_id, current_step)
    return {"result": 1}


@mandatory_params(["email", "character_id"])
def post_check_chat_room_existence(event, context, body):
    cursor = get_db_connection().cursor()

    # character_id 확인
    if not character_module.get_character(body["character_id"], cursor=cursor):
        raise IdolmasterResourceNotFoundExeption(message="character_id not found")

    # premium 구독 확인
    # if (
    #     not user_module.check_premium(body["email"])
    #     and character_module.get_character(body["character_id"], cursor=cursor)["type"]
    #     == const.CHARACTER_TYPE_MYSTERY
    # ):
    #     raise IdolmasterBadRequestException(
    #         message="Only available for premium subscribers"
    #     )

    res = chat_module.check_chatroom(body["email"], body["character_id"])
    return {
        "result": 1,
        "data": res
    }


@mandatory_params(["email", "character_ids", "language"])
def post_create_chatroom(event, context, body):
    # character_id 확인
    cursor = get_db_connection().cursor()
    if len(body["character_ids"]) != 1:
        raise IdolmasterBadRequestException(message="Invalid character_ids")
    character_id = body["character_ids"][0]
    if not character_module.get_character(character_id, cursor=cursor):
        raise IdolmasterResourceNotFoundExeption(message="character_ids not found")

    chatroom_id = chat_module.create_chatroom(
        body["email"], character_id, body["language"]
    )
    return {
        "result": 1,
        "chatroom_id": chatroom_id
    }


@mandatory_params(["chatroom_id", "send_time#user_id", "like"])
def post_evaluate_chat(event, context, body):
    send_time, email = body["send_time#user_id"].split("#")
    room_id = body["chatroom_id"]
    cursor = get_db_connection().cursor()

    # chatroom_id 확인
    if (
        not chat_module.check_active(room_id, cursor=cursor)
        and not groupchat_module.check_active(room_id, cursor=cursor)
    ):
        raise IdolmasterResourceNotFoundExeption(message="chatroom_id not found")

    # chatroom_id에 대한 권한이 있는지 확인
    if (
        not chat_module.check_member(email, room_id, cursor=cursor)
        and not groupchat_module.check_member(email, room_id)
    ):
        raise IdolmasterForbiddenException

    chat_module.set_evaluate_chat(
        email, room_id, send_time, body["like"]
    )


@mandatory_params(["email", "chatroom_id", "send_time"])
def post_get_chat_evaluation(event, context, body):
    room_id = body["chatroom_id"]
    cursor = get_db_connection().cursor()

    # chatroom_id 확인
    if (
        not chat_module.check_active(room_id, cursor=cursor)
        and not groupchat_module.check_active(room_id, cursor=cursor)
    ):
        raise IdolmasterResourceNotFoundExeption(message="chatroom_id not found")

    # chatroom_id에 대한 권한이 있는지 확인
    if (
        not chat_module.check_member(body["email"], room_id, cursor=cursor)
        and not groupchat_module.check_member(body["email"], room_id)
    ):
        raise IdolmasterForbiddenException

    res = chat_module.get_chat_evaluation(
        body["email"], room_id, body["send_time"]
    )
    return {
        "result": 1,
        "like": res
    }


@mandatory_params(["email", "chatroom_id"])
def post_get_chatroom_info(event, context, body):
    cursor = get_db_connection().cursor()

    # chatroom_id 확인
    if not chat_module.check_active(body["chatroom_id"], cursor=cursor):
        raise IdolmasterResourceNotFoundExeption(message="chatroom_id not found")

    # chatroom_id에 대한 권한이 있는지 확인
    if not chat_module.check_member(body["email"], body["chatroom_id"], cursor=cursor):
        raise IdolmasterForbiddenException

    return chat_module.get_chatroom_info(body["email"], body["chatroom_id"])


@mandatory_params(["email", "chatroom_id"])
def post_get_chatroom_info_v2(event, context, body):
    cursor = get_db_connection().cursor()

    # chatroom_id 확인
    if not chat_module.check_active(body["chatroom_id"], cursor=cursor):
        raise IdolmasterResourceNotFoundExeption(message="chatroom_id not found")

    # chatroom_id에 대한 권한이 있는지 확인
    if not chat_module.check_member(body["email"], body["chatroom_id"], cursor=cursor):
        raise IdolmasterForbiddenException

    res = chat_module.get_chatroom_info_v2(body["email"], body["chatroom_id"])
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
    chatroom_info.update(res)
    return {
        "result": 1,
        "data": chatroom_info
    }


@mandatory_params(["email"])
def post_get_chatroom_list(event, context, body):
    params = event.get("queryStringParameters")
    params = params if params else {}
    page = int(params.get("page", 1))
    page_size = int(params.get("page_size", 10))
    offset = (page - 1) * page_size
    return chat_module.list_chatroom(body["email"], page_size, offset)


@mandatory_params(["email"])
def post_get_chatroom_list_v2(event, context, body):
    params = event.get("queryStringParameters")
    params = params if params else {}
    page = int(params.get("page", 1))
    page_size = int(params.get("page_size", 10))
    offset = (page - 1) * page_size
    res = chat_module.list_chatroom_v2(body["email"], page_size, offset)
    return {
        "result": 1,
        "data": res
    }


@mandatory_params(["email", "chatroom_id"])
def post_get_previous_chat(event, context, body):
    cursor = get_db_connection().cursor()

    # chatroom_id 확인
    if not chat_module.check_active(body["chatroom_id"], cursor=cursor):
        raise IdolmasterResourceNotFoundExeption(message="chatroom_id not found")

    # chatroom_id에 대한 권한이 있는지 확인
    if not chat_module.check_member(body["email"], body["chatroom_id"], cursor=cursor):
        raise IdolmasterForbiddenException

    res = chat_module.get_previous_chat(
        body["email"], body["chatroom_id"], body.get("last_evaluated_key")
    )
    return {
        "result": 1,
        "data": res["chats"],
        "last_evaluated_key": res["last_evaluated_key"]
    }


@mandatory_params(["email", "chatroom_id"])
def post_leave_chatroom(event, context, body):
    cursor = get_db_connection().cursor()
    email = body["email"]
    chatroom_id = body["chatroom_id"]

    # chatroom_id 확인
    if not chat_module.check_active(chatroom_id, cursor=cursor):
        raise IdolmasterResourceNotFoundExeption(message="chatroom_id not found")

    # chatroom_id에 대한 권한이 있는지 확인
    if not chat_module.check_member(email, chatroom_id, cursor=cursor):
        raise IdolmasterForbiddenException

    chat_module.leave_chatroom(email, chatroom_id)
    return {
        "result": 1,
        "chatroom_id": chatroom_id
    }


@mandatory_params(["email", "chatroom_id", "subject", "explanation"])
def post_send_report(event, context, body):
    cursor = get_db_connection().cursor()

    # chatroom_id 확인
    if not chat_module.check_active(body["chatroom_id"], cursor=cursor):
        raise IdolmasterResourceNotFoundExeption(message="chatroom_id not found")

    # chatroom_id에 대한 권한이 있는지 확인
    if not chat_module.check_member(body["email"], body["chatroom_id"], cursor=cursor):
        raise IdolmasterForbiddenException

    chat_module.send_report(
        body["email"], body["chatroom_id"], body["subject"], body["explanation"]
    )
    return {"result": 1}


@mandatory_params(["email", "chatroom_id", "room_type", "notification"])
def put_set_notification(event, context, body):
    cursor = get_db_connection().cursor()

    # chatroom_id 확인
    groupchat_members = groupchat_module.list_members(body["chatroom_id"], cursor=cursor)
    if (
        not chat_module.check_active(body["chatroom_id"], cursor=cursor)
        and not groupchat_members
    ):
        raise IdolmasterResourceNotFoundExeption(message="chatroom_id not found")

    # chatroom_id에 대한 권한이 있는지 확인
    if (
        not chat_module.check_member(body["email"], body["chatroom_id"], cursor=cursor)
        and body["email"] not in groupchat_members
    ):
        raise IdolmasterForbiddenException

    # room_type 확인
    if body["room_type"] not in ["personal", "group"]:
        raise IdolmasterBadRequestException(message="Invalid room_type")

    if body["room_type"] == "personal":
        chat_module.set_notification(
            body["email"], body["chatroom_id"], body["notification"]
        )
    else:
        groupchat_module.set_notification(
            body["email"], body["chatroom_id"], body["notification"]
        )

    return {"result": 1}


# TODO check using
@mandatory_params(["chatroom_id", "value"])
def put_set_safechat(event, context, body):
    # chatroom_id 확인
    if not chat_module.check_active(body["chatroom_id"]):
        raise IdolmasterResourceNotFoundExeption(message="chatroom_id not found")

    chat_module.set_safe_chat(body["chatroom_id"], body["value"])
    return {"result": 1}
