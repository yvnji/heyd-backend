from lib.decorator import mandatory_params
from lib.exception import IdolmasterBadRequestException
from lib.exception import IdolmasterForbiddenException
from lib.exception import IdolmasterResourceNotFoundExeption
from service import character as character_module
from service import chat as chat_module
from thirdparty.mariadb import get_db_connection


@mandatory_params(["chatrooms"])
def delete_chatrooms(event, context, params):
    """채팅방 나가기
    post_leave_chatroom 수정
    """
    email = event["requestContext"]["authorizer"]["email"]
    chatroom_id = params["chatrooms"]
    cursor = get_db_connection().cursor()

    # chatroom_id 확인
    if not chat_module.check_active(chatroom_id, cursor=cursor):
        raise IdolmasterResourceNotFoundExeption(message="chatroom_id not found")

    # chatroom_id에 대한 권한이 있는지 확인
    if not chat_module.check_member(email, chatroom_id, cursor=cursor):
        raise IdolmasterForbiddenException

    chat_module.leave_chatroom(email, chatroom_id)


@mandatory_params(["chatrooms", "send_time"])
def delete_chatrooms_evaluations(event, context, params):
    """채팅 평가 삭제
    delete_evaluate_chat 수정
    send_time#user_id -> send_time
    """
    email = event["requestContext"]["authorizer"]["email"]
    chatroom_id = params["chatrooms"]
    send_time = params["send_time"]
    cursor = get_db_connection().cursor()

    # chatroom_id 확인
    if not chat_module.check_active(chatroom_id, cursor=cursor):
        raise IdolmasterResourceNotFoundExeption(message="chatroom_id not found")

    # chatroom_id에 대한 권한이 있는지 확인
    if not chat_module.check_member(email, chatroom_id, cursor=cursor):
        raise IdolmasterForbiddenException

    chat_module.delete_evaluate_chat(email, chatroom_id, send_time)


def get_chatrooms(event, context, params):
    """채팅방 정보 조회
    path parameter 값이 있으면 단일 조회, 없을 경우 복수 조회
    post_get_chatroom_info_v2, post_get_chatroom_list_v2 통합
    """
    email = event["requestContext"]["authorizer"]["email"]
    chatroom_id = params.get("chatrooms")
    cursor = get_db_connection().cursor()
    data = None

    # 단일 조회
    if chatroom_id:
        # chatroom_id 확인
        if not chat_module.check_active(chatroom_id, cursor=cursor):
            raise IdolmasterResourceNotFoundExeption(message="chatroom_id not found")

        # chatroom_id에 대한 권한이 있는지 확인
        if not chat_module.check_member(email, chatroom_id, cursor=cursor):
            raise IdolmasterForbiddenException

        data = chat_module.get_chatroom_info_v2(email, chatroom_id)

    # 리스트로 조회
    else:
        page = int(params.get("page", 1))
        page_size = int(params.get("page_size", 10))
        offset = (page - 1) * page_size
        data = chat_module.list_chatroom_v2(email, page_size, offset)

    return {"data": data}


@mandatory_params(["chatrooms"])
def get_chatrooms_chats(event, context, params):
    """채팅 목록 조회
    post_get_previous_chat 수정
    query parameter limit 추가
    """
    email = event["requestContext"]["authorizer"]["email"]
    chatroom_id = params["chatrooms"]
    last_evaluated_key = params.get("last_evaluated_key")
    cursor = get_db_connection().cursor()

    # limit 타입 확인
    try:
        limit = int(params.get("limit", 50))
    except ValueError:
        raise IdolmasterBadRequestException(
            message="Invalid params",
            result_code=1)

    # chatroom_id 확인
    if not chat_module.check_active(chatroom_id, cursor=cursor):
        raise IdolmasterResourceNotFoundExeption(message="chatroom_id not found")

    # chatroom_id에 대한 권한이 있는지 확인
    if not chat_module.check_member(email, chatroom_id, cursor=cursor):
        raise IdolmasterForbiddenException

    res = chat_module.get_previous_chat(
        email, chatroom_id, last_evaluated_key, limit=limit
    )
    return {
        "data": res["chats"],
        "last_evaluated_key": res["last_evaluated_key"]
    }


@mandatory_params(["chatrooms", "send_time"])
def get_chatrooms_evaluations(event, context, params):
    """채팅 평가 내역 조회
    post_get_chat_evaluation 이름 변경
    return 변경
    """
    email = event["requestContext"]["authorizer"]["email"]
    chatroom_id = params["chatrooms"]
    send_time = params["send_time"]
    cursor = get_db_connection().cursor()

    # chatroom_id 확인
    if not chat_module.check_active(chatroom_id, cursor=cursor):
        raise IdolmasterResourceNotFoundExeption(message="chatroom_id not found")

    # chatroom_id에 대한 권한이 있는지 확인
    if not chat_module.check_member(email, chatroom_id, cursor=cursor):
        raise IdolmasterForbiddenException

    res = chat_module.get_chat_evaluation(
        email, chatroom_id, send_time
    )
    return {
        "data": {
            "like": res
        }
    }


@mandatory_params(["character_id", "language"])
def post_chatrooms(event, context, body):
    """채팅방 생성
    post_create_chatroom 수정
    body parameter character_ids -> character_id
    return 변경
    """
    email = event["requestContext"]["authorizer"]["email"]
    character_id = body["character_id"]
    language = body["language"]

    # character_id 확인
    cursor = get_db_connection().cursor()
    if not character_module.get_character(character_id, cursor=cursor):
        raise IdolmasterResourceNotFoundExeption(message="character_id not found")

    chatroom_id = chat_module.create_chatroom(
        email, character_id, language
    )
    return {
        "data": {
            "chatroom_id": chatroom_id
        }
    }


@mandatory_params(["chatrooms", "send_time", "like"])
def post_chatrooms_evaluations(event, context, body):
    """채팅 평가 등록
    post_evaluate_chat 이름 변경
    body send_time#user_id -> send_time
    """
    email = event["requestContext"]["authorizer"]["email"]
    chatroom_id = body["chatrooms"]
    send_time = body["send_time"]
    like = body["like"]
    cursor = get_db_connection().cursor()

    # chatroom_id 확인
    if not chat_module.check_active(chatroom_id, cursor=cursor):
        raise IdolmasterResourceNotFoundExeption(message="chatroom_id not found")

    # chatroom_id에 대한 권한이 있는지 확인
    if not chat_module.check_member(email, chatroom_id, cursor=cursor):
        raise IdolmasterForbiddenException

    chat_module.set_evaluate_chat(
        email, chatroom_id, send_time, like
    )


@mandatory_params(["chatrooms", "subject", "explanation"])
def post_chatrooms_reports(event, context, body):
    """채팅방 신고하기
    post_send_report 수정
    """
    email = event["requestContext"]["authorizer"]["email"]
    chatroom_id = body["chatrooms"]
    subject = body["subject"]
    explanation = body["explanation"]
    cursor = get_db_connection().cursor()

    # chatroom_id 확인
    if not chat_module.check_active(chatroom_id, cursor=cursor):
        raise IdolmasterResourceNotFoundExeption(message="chatroom_id not found")

    # chatroom_id에 대한 권한이 있는지 확인
    if not chat_module.check_member(email, chatroom_id, cursor=cursor):
        raise IdolmasterForbiddenException

    chat_module.send_report(
        email, chatroom_id, subject, explanation
    )


@mandatory_params(["chatrooms", "notification"])
def put_chatrooms_notifications(event, context, body):
    """채팅방 알림 설정
    put_set_notification에서 1:1 채팅방 기능 분리
    body room_type 삭제
    """
    email = event["requestContext"]["authorizer"]["email"]
    chatroom_id = body["chatrooms"]
    noti = body["notification"]
    cursor = get_db_connection().cursor()

    # chatroom_id 확인
    if not chat_module.check_active(chatroom_id, cursor=cursor):
        raise IdolmasterResourceNotFoundExeption(message="chatroom_id not found")

    # chatroom_id에 대한 권한이 있는지 확인
    if not chat_module.check_member(email, chatroom_id, cursor=cursor):
        raise IdolmasterForbiddenException

    chat_module.set_notification(
        email, chatroom_id, noti
    )


@mandatory_params(["chatrooms", "value"])
def put_chatrooms_safe(event, context, body):
    """put_set_safechat 수정
    """
    email = event["requestContext"]["authorizer"]["email"]
    chatroom_id = body["chatrooms"]
    value = body["value"]
    cursor = get_db_connection().cursor()

    # chatroom_id 확인
    if not chat_module.check_active(chatroom_id, cursor=cursor):
        raise IdolmasterResourceNotFoundExeption(message="chatroom_id not found")

    # chatroom_id에 대한 권한이 있는지 확인
    if not chat_module.check_member(email, chatroom_id, cursor=cursor):
        raise IdolmasterForbiddenException

    chat_module.set_safe_chat(chatroom_id, value)


@mandatory_params(["chatrooms", "step"])
def put_chatrooms_mystery_steps(event, context, body):
    """추리게임 채팅방 단계 업데이트
    delete_update_mystery_chat_step 수정
    """
    email = event["requestContext"]["authorizer"]["email"]
    chatroom_id = body["chatrooms"]
    current_step = body["step"]
    cursor = get_db_connection().cursor()

    # chatroom_id 확인
    if not chat_module.check_active(chatroom_id, cursor=cursor):
        raise IdolmasterResourceNotFoundExeption(message="chatroom_id not found")

    # chatroom_id에 대한 권한이 있는지 확인
    if not chat_module.check_member(email, chatroom_id, cursor=cursor):
        raise IdolmasterForbiddenException

    # step 확인
    if current_step not in ["Introduction", "Guessing", "Choices", "Conclusion", "GameOver"]:
        raise IdolmasterBadRequestException(
            message="Invalid params",
            result_code=1)

    chat_module.update_mystery_chat_step(email, chatroom_id, current_step)
