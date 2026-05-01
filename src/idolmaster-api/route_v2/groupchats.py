from lib.decorator import mandatory_params
from lib.exception import IdolmasterBadRequestException
from lib.exception import IdolmasterConflictResourceException
from lib.exception import IdolmasterForbiddenException
from lib.exception import IdolmasterResourceNotFoundExeption
from lib.parser import convert_to_bool
from service import character as character_module
from service import groupchat as groupchat_module
from thirdparty.mariadb import get_db_connection


@mandatory_params(["groupchats"])
def delete_groupchats_connections(event, context, params):
    """그룹채팅방 나가기
    post_leave_chatroom 수정
    """
    email = event["requestContext"]["authorizer"]["email"]
    groupchat_id = params["groupchats"]

    # groupchat_id 확인
    chat_members = groupchat_module.list_members(groupchat_id)
    if not chat_members:
        raise IdolmasterResourceNotFoundExeption(message="groupchat_id not found")
    if email not in chat_members:
        raise IdolmasterConflictResourceException

    groupchat_module.leave_chatroom(email, groupchat_id)


def get_groupchats(event, context, params):
    """채팅방 정보 조회
    post_get_chatroom_info, post_get_groupchat_list 통합
    """
    email = event["requestContext"]["authorizer"]["email"]
    groupchat_id = params.get("groupchats")
    ret = None

    # 채팅방 단일 조회
    if groupchat_id:
        # groupchat_id 확인
        chat_members = groupchat_module.list_members(groupchat_id)
        if not chat_members:
            raise IdolmasterResourceNotFoundExeption(message="groupchat_id not found")

        # 채팅방 멤버인지 확인
        if not groupchat_module.check_member(email, groupchat_id).get("is_member"):
            raise IdolmasterForbiddenException

        ret = groupchat_module.get_chatroom_info(email, groupchat_id)
        return {"data": ret}

    # 채팅방 리스트 조회
    else:
        search_keyword = params.get("search", "")
        room_accessibility = params.get("type", "").lower()

        # check type
        try:
            page = int(params.get("page", 1))
            page_size = int(params.get("page_size", 10))
            offset = (page - 1) * page_size
            if page < 1 or page_size < 1:
                raise ValueError
            if room_accessibility and room_accessibility not in ("public", "private"):
                raise ValueError
        except ValueError:
            raise IdolmasterBadRequestException(
                message="Invalid params",
                result_code=1)

        ret = groupchat_module.list_groupchat(
            email, page_size, room_accessibility, search_keyword, offset
        )
        return {
            "data": ret["chats"],
            "total": ret["total_count"]
        }


@mandatory_params(["groupchats"])
def get_groupchats_chats(event, context, params):
    """채팅 목록 조회
    post_get_previous_chat 수정
    """
    email = event["requestContext"]["authorizer"]["email"]
    groupchat_id = params["groupchats"]
    last_evaluated_key = params.get("last_evaluated_key")

    # groupchat_id 확인
    chat_members = groupchat_module.list_members(groupchat_id)
    if not chat_members:
        raise IdolmasterResourceNotFoundExeption(message="groupchat_id not found")

    res = groupchat_module.get_previous_chat(
        email, groupchat_id, last_evaluated_key
    )
    return {
        "data": res["chats"],
        "last_evaluated_key": res["last_evaluated_key"]
    }


@mandatory_params(["groupchats"])
def get_groupchats_connections(event, context, params):
    """그룹채팅방 멤버인지 확인
    post_check_member 수정
    """
    email = event["requestContext"]["authorizer"]["email"]
    groupchat_id = params["groupchats"]

    # groupchat_id 확인
    chat_members = groupchat_module.list_members(groupchat_id)
    if not chat_members:
        raise IdolmasterResourceNotFoundExeption(message="groupchat_id not found")

    res = groupchat_module.check_member(email, groupchat_id)
    return {"data": res}


@mandatory_params(
    [
        "character_ids",
        "name",
        "description",
        "accessibility",
        "password",
        "max_participants_num",
        "language",
    ]
)
def post_groupchats(event, context, body):
    """그룹채팅방 생성
    post_create_chatroom 수정
    """
    email = event["requestContext"]["authorizer"]["email"]
    character_ids = body["character_ids"]
    name = body["name"]
    description = body["description"]
    access = body["accessibility"].lower()
    password = body["password"]
    language = body["language"]
    cursor = get_db_connection().cursor()

    # check type
    try:
        participants = int(body["max_participants_num"])
        if access not in ("private", "public"):
            raise ValueError
    except ValueError:
        raise IdolmasterBadRequestException(
            message="Invalid params",
            result_code=1)

    # character_id 확인
    for character_id in character_ids:
        if not character_module.get_character(character_id, cursor=cursor):
            raise IdolmasterResourceNotFoundExeption(message="character_ids not found")

    groupchat_id = groupchat_module.create_chatroom(
        email,
        character_ids,
        name,
        description,
        access,
        password,
        participants,
        language,
    )
    return {
        "data": {
            "groupchat_id": groupchat_id
        }
    }


@mandatory_params(["groupchats", "accessibility"])
def post_groupchats_connections(event, context, body):
    """그룹채팅방 입장
    post_enter_groupchat 수정
    """
    email = event["requestContext"]["authorizer"]["email"]
    groupchat_id = body["groupchats"]
    access = body["accessibility"]
    password = body.get("password")

    # groupchat_id 확인
    chat_members = groupchat_module.list_members(groupchat_id)
    if not chat_members:
        raise IdolmasterResourceNotFoundExeption(message="groupchat_id not found")

    status_code = groupchat_module.enter_groupchat(
        email, groupchat_id, access, password
    )
    print(f"groupchats_connections status_code : {status_code}")

    if not status_code:
        return
    elif status_code == 3:
        raise IdolmasterConflictResourceException(message="This room is full")
    elif status_code == 4:
        raise IdolmasterForbiddenException(message="Password does not match")

    # status_code == 1 or 2 : 위에서 groupchat_id 확인 실패
    else:
        raise Exception


@mandatory_params(["groupchats", "notification"])
def put_groupchats_notifications(event, context, body):
    """그룹채팅방 알림 설정
    chat.put_set_notification에서 그룹채팅방 알림만 분리
    body room_type 삭제
    """
    email = event["requestContext"]["authorizer"]["email"]
    groupchat_id = body["groupchats"]

    try:
        noti = convert_to_bool(body["notification"])
    except ValueError:
        raise IdolmasterBadRequestException(
            message="Invalid notification",
            result_code=1)

    # groupchat_id 확인
    if not groupchat_module.check_active(groupchat_id):
        raise IdolmasterResourceNotFoundExeption(message="groupchat_id not found")

    # 채팅방 멤버인지 확인
    if not groupchat_module.check_member(email, groupchat_id).get("is_member"):
        raise IdolmasterForbiddenException

    groupchat_module.set_notification(
        email, groupchat_id, noti
    )


@mandatory_params(["groupchats", "users", "block"])
def put_groupchats_users_block(event, context, body):
    """그룹채팅방 내에서 다른 사용자 차단 설정
    post_block_user 수정
    post, delete 합치면서 body에 block 추가 (block : 차단 유무)
    """
    email = event["requestContext"]["authorizer"]["email"]
    groupchat_id = body["groupchats"]
    user_email = body["users"]  # 차단 할 사용자 email
    block = body["block"]

    # groupchat_id 확인
    chat_members = groupchat_module.list_members(groupchat_id)
    if not chat_members:
        raise IdolmasterResourceNotFoundExeption(message="groupchat_id not found")
    if email not in chat_members:
        raise IdolmasterForbiddenException
    if user_email not in chat_members:
        raise IdolmasterConflictResourceException

    groupchat_module.update_block_user(
        email, groupchat_id, user_email, block
    )
