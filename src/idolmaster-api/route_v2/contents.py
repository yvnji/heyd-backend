import const
from lib.decorator import mandatory_params
from lib.decorator import preprocessing_cursor
from lib.exception import (IdolmasterBadRequestException,
                           IdolmasterConflictResourceException,
                           IdolmasterForbiddenException,
                           IdolmasterResourceNotFoundExeption)
from lib.moderation import moderate_image
from lib.parser import convert_to_bool
from service import chatroom as chatroom_module
from service import content as content_module
from service import product as product_module
from service import reaction as reaction_module


@mandatory_params(["contents"])
def delete_contents(event, context, params):
    """컨텐츠 삭제"""
    user_id = int(event["requestContext"]["authorizer"]["db_id"])
    content_id = params["contents"]

    # check content_id
    content_item = content_module.get_content(content_id)
    if not content_item:
        raise IdolmasterResourceNotFoundExeption(message="content_id not found")
    content_id = int(content_id)
    if user_id != content_item["creator_id"]:
        raise IdolmasterForbiddenException

    # 컨텐츠 비활성화
    content_module.deactivate_content(content_id)


def get_contents(event, context, params):
    """컨텐츠 조회"""
    user_id = int(event["requestContext"]["authorizer"]["db_id"])
    email = event["requestContext"]["authorizer"]["email"]
    content_id = params.get("contents")
    ret = None

    # check params
    try:
        content_type = params.get("type", const.CONTENT_TYPE_CHATROOM)
        assert content_type in (const.CONTENT_TYPE_CHATROOM)
    except AssertionError:
        raise IdolmasterBadRequestException(message="Invalid params", result_code=1)

    # 단일 상세 조회
    if content_id:
        ret = {}
        if content_type == const.CONTENT_TYPE_CHATROOM:
            ret = content_module.get_content_chatroom_detail(content_id, email=email, user_id=user_id)
            if ret:
                if ret.get("chatroom_activated"):
                    ret["active"] = True
                else:
                    ret["active"] = False
                del ret["chatroom_activated"]

    # 리스트 조회
    else:
        ret = []
        if content_type == const.CONTENT_TYPE_CHATROOM:
            own = params.get("own", False)
            search = params.get("search")
            category = params.get("category")
            ch_activated = params.get("activated", False)
            ch_liked = params.get("liked", False)
            main = category == const.CONTENT_CATEGORY_MAIN

            # check params
            try:
                # 정렬 기준
                # 1: 컨텐츠 생성 시간 내림차순
                # 2: 좋아요 수 내림차순
                # 3: 사용자 수 내림차순
                # 4: 사용자 최신 이용 내림차순
                order_type = int(params.get("order_type", 1))

                own = convert_to_bool(own)
                ch_activated = convert_to_bool(ch_activated)
                ch_liked = convert_to_bool(ch_liked)
                rating = params.get("rating", const.CONTENT_RATING_GENERAL).upper()
                page = int(params.get("page", 1))
                page_size = int(params.get("page_size", 20))
                offset = (page - 1) * page_size
                assert 1 <= page and 1 <= page_size
                assert rating in (const.CONTENT_RATING_ADULT, const.CONTENT_RATING_GENERAL)
                assert order_type in [1, 2, 3, 4]
            except (ValueError, AssertionError):
                raise IdolmasterBadRequestException(message="Invalid params", result_code=1)

            ret = content_module.list_content_chatroom(
                rating,
                order_type,
                user_id=user_id,
                search=search,
                category=category if not main else None,
                own=own,
                activated=ch_activated,
                liked=ch_liked,
                main=main,
                page_size=page_size,
                offset=offset
            )

            # 검색어 이력 저장
            if search:
                content_module.save_search_history(user_id, search)

    return {"data": ret}


@mandatory_params(["contents"])
def get_contents_chats(event, context, params):
    """채팅 내역 조회"""
    user_id = int(event["requestContext"]["authorizer"]["db_id"])
    content_id = params["contents"]
    last_evaluated_key = params.get("last_evaluated_key")

    # check type
    try:
        limit = int(params.get("limit", 50))
    except ValueError:
        raise IdolmasterBadRequestException(message="Invalid params", result_code=1)

    # 컨텐츠 ID 확인
    content_item = content_module.get_content(content_id)
    if not content_item:
        raise IdolmasterResourceNotFoundExeption(message="content_id not found")
    content_id = int(content_id)

    # 컨텐츠 type 확인
    if content_item["type"] != const.CONTENT_TYPE_CHATROOM:
        raise IdolmasterBadRequestException(message="Invalid content type", result_code=2)

    # 활성화 확인
    chatroom_activated = chatroom_module.get_chatroom_activated(user_id, content_id=content_id)
    if not chatroom_activated:
        raise IdolmasterBadRequestException(message="Content is not activated", result_code=3)

    data = chatroom_module.list_chat(
        chatroom_activated["id"],
        chatroom_activated["start_at"],
        last_evaluated_key=last_evaluated_key,
        limit=limit)

    # response 형식 변경
    data_ret = []
    for chat in data["chats"]:
        item = {
            "timestamp_at": chat["timestamp_at"],
            "chat": chat["chat"]
        }
        if chat.get("user_id"):
            item["sender"] = {
                "character_id": None,
                "nickname": chat["user_nickname"],
                "type": 2
            }
            item["receiver"] = {
                "character_id": chat["character_id"],
                "nickname": chat["character_name"]
            }
        else:
            item["receiver"] = None
            item["sender"] = {
                "character_id": chat["character_id"],
                "nickname": chat["character_name"],
                "type": 1
            }
        data_ret.append(item)

    return {
        "data": data_ret,
        "last_evaluated_key": data["last_evaluated_key"]
    }


@mandatory_params([
    "thumbnail_id", "title", "description", "type", "rating"])
@preprocessing_cursor
def post_contents(event, context, body, cursor=None):
    """컨텐츠 생성"""
    user_id = int(event["requestContext"]["authorizer"]["db_id"])
    thumbnail_id = body["thumbnail_id"]
    title = body["title"]
    description = body["description"]
    content_type = body["type"].lower()
    rating = body["rating"].upper()
    chatroom_id = body.get("chatroom_id")
    tags = body.get("tags")
    tag_list = tags.replace(" ", "").split(",") if tags else None

    # check body
    try:
        assert len(title) <= 50
        assert len(description) <= 500
        assert content_type in (const.CONTENT_TYPE_CHATROOM)
        assert rating in (const.CONTENT_RATING_ADULT, const.CONTENT_RATING_GENERAL)
        thumbnail_id = int(thumbnail_id)
        if chatroom_id:
            chatroom_id = int(chatroom_id)
    except (AssertionError, ValueError):
        raise IdolmasterBadRequestException(message="Invalid params", result_code=1)

    # check file id
    if not content_module.get_thumbnail(thumbnail_id, cursor=cursor):
        raise IdolmasterResourceNotFoundExeption(message="thumbnail_id not found")

    # 채팅방 컨텐츠 생성
    if content_type == const.CONTENT_TYPE_CHATROOM:
        # 채팅방 확인
        if not chatroom_id or not chatroom_module.get_chatroom(chatroom_id, cursor=cursor):
            raise IdolmasterResourceNotFoundExeption(message="chatroom_id not found", result_code=1)

        content_id = content_module.create_content(
            title,
            description,
            thumbnail_id,
            content_type,
            rating,
            user_id,
            cursor=cursor
        )
        content_module.connect_content_chatroom(content_id, chatroom_id, cursor=cursor)
        target_id = reaction_module.get_reaction_id(content_id=content_id, cursor=cursor)

        # tag 생성
        if tag_list:
            reaction_module.create_tag(target_id, tag_list, cursor=cursor)

        return {"data": {"content_id": content_id}}


@mandatory_params(["contents", "chat", "character_id"])
def post_contents_chats(event, context, body):
    """채팅 입력"""
    user_id = int(event["requestContext"]["authorizer"]["db_id"])
    email = event["requestContext"]["authorizer"]["email"]
    content_id = body["contents"]
    character_id = body["character_id"]
    chat = body["chat"]
    # body 딕셔너리에 "block_reason" 키가 있으면 해당 값을 사용하고, 없으면 None을 할당합니다.
    block_reason = body.get("block_reason", "")

    # check content_id
    content_item = content_module.get_content_chatroom_detail(content_id, email=email, user_id=user_id)
    if not content_item:
        raise IdolmasterResourceNotFoundExeption(message="content_id not found")
    content_id = int(content_id)

    # 컨텐츠 type 확인
    if content_item["type"] != const.CONTENT_TYPE_CHATROOM:
        raise IdolmasterBadRequestException(message="Invalid content type", result_code=1)

    # character_id 확인
    character_ids = [c["character_id"] for c in content_item["chatroom"]["characters"]]
    if character_id not in character_ids:
        raise IdolmasterResourceNotFoundExeption(message="character_id not found", result_code=1)
    character_ids.remove(character_id)
    character_ids = [character_id] + character_ids

    # 활성화 확인
    if not content_item["chatroom_activated"]:
        raise IdolmasterBadRequestException(message="contents is not activated", result_code=2)

    # 다트 확인
    product_item = product_module.get_product(email)
    if product_item["dart"] <= 0:
        raise IdolmasterBadRequestException(message="Not enough darts to proceed")

    # AI answer
    res = chatroom_module.send_chat(
        character_ids,
        const.CHAT_TYPE_CONTENT,
        chat,
        start_at=content_item["chatroom_activated"]["start_at"],
        user_id=user_id,
        chatroom_activated_id=content_item["chatroom_activated"]["id"],
        block_reason=block_reason
    )

    # 다트 차감 (검열 통과 시에만)
    if res["block_reason"]:
        res["dart_remained"] = product_item["dart"]
    else:
        check_dart = product_module.decrease_product(email, const.PRODUCT_CHARGE_TYPE_DEDUCT_MESSAGE)
        res["dart_remained"] = check_dart["remain"]["dart"]

    return {"data": res}


@mandatory_params(["contents", "detail"])
def post_contents_reports(event, context, body):
    """컨텐츠 신고"""
    user_id = int(event["requestContext"]["authorizer"]["db_id"])
    content_id = body["contents"]
    detail = body["detail"]

    # check content_id
    content_item = content_module.get_content(content_id)
    if not content_item:
        raise IdolmasterResourceNotFoundExeption(message="content_id not found")
    content_id = int(content_id)

    # 신고 등록
    target_id = reaction_module.get_reaction_id(content_id=content_id)
    reaction_module.submit_report(target_id, user_id, detail)


@mandatory_params(["contents"])
def post_contents_reset_chats(event, context, body):
    """컨텐츠 채팅방 초기화"""
    user_id = int(event["requestContext"]["authorizer"]["db_id"])
    email = event["requestContext"]["authorizer"]["email"]
    content_id = body["contents"]

    # check content_id
    content_item = content_module.get_content_chatroom_detail(content_id, email=email, user_id=user_id)
    if not content_item:
        raise IdolmasterResourceNotFoundExeption(message="content_id not found")
    content_id = int(content_id)

    # 컨텐츠 type 확인
    if content_item["type"] != const.CONTENT_TYPE_CHATROOM:
        raise IdolmasterBadRequestException(message="Invalid content type", result_code=1)

    # 활성화 확인
    if not content_item["chatroom_activated"]:
        raise IdolmasterBadRequestException(message="Content is not activated", result_code=2)

    chatroom_module.reset_chatroom_activated(
        content_item["chatroom"]["id"],
        content_item["chatroom_activated"]["id"]
    )


@mandatory_params(["contents", "thumbnail_id", "title", "description", "rating", "chatroom_id", "tags"])
@preprocessing_cursor
def put_contents(event, context, body, cursor=None):
    """컨텐츠 정보 수정"""
    user_id = int(event["requestContext"]["authorizer"]["db_id"])
    content_id = body["contents"]
    thumbnail_id = body["thumbnail_id"]
    title = body["title"]
    description = body["description"]
    rating = body["rating"].upper()
    chatroom_id = body.get("chatroom_id")
    tags = body.get("tags")
    tag_list = sorted(list(set(tags.replace(" ", "").split(",")))) if tags else None

    # check body
    try:
        assert len(title) <= 50
        assert len(description) <= 200
        assert rating in (const.CONTENT_RATING_ADULT, const.CONTENT_RATING_GENERAL)
        thumbnail_id = int(thumbnail_id)
        if chatroom_id:
            chatroom_id = int(chatroom_id)
    except (AssertionError, ValueError):
        raise IdolmasterBadRequestException(message="Invalid params", result_code=1)

    # check content_id
    content_item = content_module.get_content(content_id, cursor=cursor)
    if not content_item:
        raise IdolmasterResourceNotFoundExeption(message="content_id not found")
    content_id = int(content_id)
    if user_id != content_item["creator_id"]:
        raise IdolmasterForbiddenException

    # check file id
    if not content_module.get_thumbnail(thumbnail_id, cursor=cursor):
        raise IdolmasterResourceNotFoundExeption(message="thumbnail_id not found", result_code=1)

    # 채팅방 컨텐츠
    if content_item["type"] == const.CONTENT_TYPE_CHATROOM:
        content_item = content_module.get_content_chatroom_detail(content_id, cursor=cursor)

        # 채팅방 확인
        if chatroom_id:
            if not chatroom_module.get_chatroom(chatroom_id, cursor=cursor):
                raise IdolmasterResourceNotFoundExeption(message="chatroom_id not found", result_code=2)
            if chatroom_id != content_item["chatroom"]["id"]:
                content_module.disconnect_content_chatroom(
                    content_id,
                    chatroom_id=content_item["chatroom"]["id"],
                    cursor=cursor)
                content_module.connect_content_chatroom(content_id, chatroom_id, cursor=cursor)

        # 컨텐츠 정보 수정
        content_module.update_content(
            content_id,
            title,
            description,
            thumbnail_id,
            rating,
            cursor=cursor
        )

        # 태그 수정
        if tag_list != content_item["tags"]:
            target_id = reaction_module.get_reaction_id(content_id=content_id, cursor=cursor)
            reaction_module.delete_tag(target_id, tag_list=content_item["tags"], cursor=cursor)
            reaction_module.create_tag(target_id, tag_list, cursor=cursor)


@mandatory_params(["contents", "activate"])
def put_contents_activates(event, context, body):
    """컨텐츠 활성화 (입장/나가기)"""
    user_id = int(event["requestContext"]["authorizer"]["db_id"])
    content_id = body["contents"]
    activate = body["activate"]
    res = False

    # check body
    try:
        activate = convert_to_bool(activate)
    except ValueError:
        raise IdolmasterBadRequestException(message="Invalid params", result_code=1)

    # check content_id
    content_item = content_module.get_content(content_id)
    if not content_item:
        raise IdolmasterResourceNotFoundExeption(message="content_id not found")
    content_id = int(content_id)

    # 채팅방 컨텐츠
    if content_item["type"] == const.CONTENT_TYPE_CHATROOM:
        chatroom_item = chatroom_module.get_chatroom_by_content(content_id)
        chatroom_id = chatroom_item["id"]

        # 활성화 확인
        chatroom_activated = chatroom_module.get_chatroom_activated(user_id, content_id=content_id)
        if (
            (chatroom_activated and activate)
            or (not chatroom_activated and not activate)
        ):
            raise IdolmasterConflictResourceException(message="Conflict resource")

        # 활성화 적용
        content_module.activate_content_chatroom(
            chatroom_id,
            chatroom_item["connect_id"],
            user_id,
            activate
        )
        res = True

    # TODO 다른 컨텐츠 타입일 경우 추가
    assert res


@mandatory_params(["contents", "register"])
def put_contents_blocks(event, context, body):
    """컨텐츠 숨기기 등록/취소"""
    user_id = int(event["requestContext"]["authorizer"]["db_id"])
    content_id = body["contents"]
    register = body["register"]

    # check type
    try:
        register = convert_to_bool(register)
    except ValueError:
        raise IdolmasterBadRequestException(message="Invalid params", result_code=1)

    # check content_id
    content_item = content_module.get_content(content_id)
    if not content_item:
        raise IdolmasterResourceNotFoundExeption(message="content_id not found")
    content_id = int(content_id)
    target_id = reaction_module.get_reaction_id(content_id=content_id)

    # 숨기기 상태 확인
    if register == reaction_module.get_block(target_id, user_id):
        raise IdolmasterConflictResourceException

    if register:
        reaction_module.submit_block(target_id, user_id)
    else:
        reaction_module.cancel_block(target_id, user_id)


@mandatory_params(["contents", "emojis", "register"])
def put_contents_emojis(event, context, body):
    """컨텐츠 이모지 등록/취소"""
    user_id = int(event["requestContext"]["authorizer"]["db_id"])
    email = event["requestContext"]["authorizer"]["email"]
    content_id = body["contents"]
    emoji_id = body["emojis"]
    register = body["register"]

    # check type
    try:
        register = convert_to_bool(register)
        emoji_id = int(emoji_id)
        assert emoji_id in [e["emoji_id"] for e in reaction_module.list_emoji()]
    except (ValueError, AssertionError):
        raise IdolmasterBadRequestException(message="Invalid params", result_code=1)

    # check content_id
    content_item = content_module.get_content_chatroom_detail(content_id, email=email, user_id=user_id)
    if not content_item:
        raise IdolmasterResourceNotFoundExeption(message="content_id not found")
    content_id = int(content_id)

    # 현재 이모지 등록 상태 조회
    target_id = reaction_module.get_reaction_id(content_id=content_id)
    register_latest = reaction_module.get_emoji_status(target_id, email, emoji_id)
    if register == register_latest:
        raise IdolmasterConflictResourceException

    if register:
        reaction_module.submit_emoji(target_id, email, emoji_id)
    else:
        reaction_module.cancel_emoji(target_id, email, emoji_id)


@mandatory_params(["contents", "register"])
def put_contents_likes(event, context, body):
    """컨텐츠 좋아요 등록/취소"""
    user_id = int(event["requestContext"]["authorizer"]["db_id"])
    email = event["requestContext"]["authorizer"]["email"]
    content_id = body["contents"]
    like = body["register"]

    # check type
    try:
        like = convert_to_bool(like)
    except ValueError:
        raise IdolmasterBadRequestException(message="Invalid params", result_code=1)

    # check content_id
    content_item = content_module.get_content_chatroom_detail(content_id, email=email, user_id=user_id)
    if not content_item:
        raise IdolmasterResourceNotFoundExeption(message="content_id not found")
    content_id = int(content_id)

    # 현재 좋아요 상태 조회
    target_id = reaction_module.get_reaction_id(content_id=content_id)
    like_latest = reaction_module.get_like_status(target_id, email)
    if like == like_latest:
        raise IdolmasterConflictResourceException

    if like:
        reaction_module.submit_like(target_id, email)
    else:
        reaction_module.cancel_like(target_id, email)


#######################################################
# path 시작이 /contents/ 아닌 API
#######################################################


def get_contents_backgrounds(event, context, params):
    """배경화면 리스트 조회"""
    user_id = int(event["requestContext"]["authorizer"]["db_id"])
    basic = params.get("basic", True)

    # check type
    try:
        basic = convert_to_bool(basic)
    except ValueError:
        raise IdolmasterBadRequestException(message="Invalid params", result_code=1)

    if basic:
        data = content_module.list_background_file_path()
    else:
        data = content_module.list_background_file_path(user_id=user_id)

    for d in data:
        del d["user_id"]
        d["file_path"] = "/" + d["file_path"]
    return {"data": data}


def get_contents_bgms(event, context, params):
    """배경음악 리스트 조회"""
    user_id = int(event["requestContext"]["authorizer"]["db_id"])
    basic = params.get("basic", True)

    # check type
    try:
        basic = convert_to_bool(basic)
    except ValueError:
        raise IdolmasterBadRequestException(message="Invalid params", result_code=1)

    if basic:
        data = content_module.list_bgm_file_path()
    else:
        data = content_module.list_bgm_file_path(user_id=user_id)

    for d in data:
        del d["user_id"]
        target_id = reaction_module.get_reaction_id(bgm_id=d["id"])
        tag_list = reaction_module.list_tag(target_id)
        d["tags"] = ",".join([t["tag"] for t in tag_list])
        d["file_path"] = "/" + d["file_path"]

    return {"data": data}


def get_contents_search_histories(event, context, params):
    """컨텐츠 검색어 이력 조회"""
    user_id = int(event["requestContext"]["authorizer"]["db_id"])
    data = content_module.list_search(user_id)
    return {"data": data}


@mandatory_params(["file", "name"])
def post_contents_backgrounds(event, context, body):
    """배경화면 등록"""
    user_id = int(event["requestContext"]["authorizer"]["db_id"])
    img_file = body["file"]
    name = body["name"]
    basic = body.get("basic", 0)

    # check type
    try:
        basic = convert_to_bool(basic)
    except ValueError:
        raise IdolmasterBadRequestException(message="Invalid params", result_code=1)

    # 배경화면 파일 검열
    is_censored = moderate_image(img_object=img_file["data"])
    print(f"is_censored: {is_censored}")
    if is_censored:
        raise IdolmasterBadRequestException(
            message="Inappropriate image", result_code=2
        )

    # 파일 S3 저장
    print(f"filename : {img_file['filename']}")
    extension = (
        img_file["filename"].split(".")[-1] if "." in img_file["filename"] else ""
    )
    img_file_path = content_module.put_file_to_s3(
        const.S3_KEY_CONTENT_BACKGROUND, img_file["data"], extension=extension
    )

    # DB 저장
    img_id = content_module.save_background_file_path(img_file_path, name, user_id, basic)

    return {"data": {
        "background_id": img_id,
        "file_path": "/" + img_file_path
    }}


@mandatory_params(["file", "name"])
def post_contents_bgms(event, context, body):
    """배경음악 등록"""
    user_id = int(event["requestContext"]["authorizer"]["db_id"])
    bgm_file = body["file"]
    name = body["name"]
    basic = body.get("basic", 0)
    tags = body.get("tags")
    tag_list = tags.replace(" ", "").split(",") if tags else None

    # check type
    try:
        basic = convert_to_bool(basic)
    except ValueError:
        raise IdolmasterBadRequestException(message="Invalid params", result_code=1)

    # 파일 S3 저장
    print(f"filename : {bgm_file['filename']}")
    extension = (
        bgm_file["filename"].split(".")[-1] if "." in bgm_file["filename"] else ""
    )
    bgm_file_path = content_module.put_file_to_s3(
        const.S3_KEY_CONTENT_BGM, bgm_file["data"], extension=extension
    )

    # DB 저장
    bgm_id = content_module.save_bgm_file_path(bgm_file_path, name, user_id, basic, tags=tag_list)

    return {"data": {
        "bgm_id": bgm_id,
        "file_path": "/" + bgm_file_path
    }}


@mandatory_params(["file"])
def post_contents_thumbnails(event, context, body):
    """썸네일 등록"""
    user_id = int(event["requestContext"]["authorizer"]["db_id"])
    img_file = body["file"]
    basic = body.get("basic", 0)

    # check type
    try:
        basic = convert_to_bool(basic)
    except ValueError:
        raise IdolmasterBadRequestException(message="Invalid params", result_code=1)

    # 썸네일 파일 검열
    is_censored = moderate_image(img_object=img_file["data"])
    print(f"is_censored: {is_censored}")
    if is_censored:
        raise IdolmasterBadRequestException(
            message="Inappropriate image", result_code=2
        )

    # 파일 S3 저장
    print(f"filename : {img_file['filename']}")
    extension = (
        img_file["filename"].split(".")[-1] if "." in img_file["filename"] else ""
    )
    img_file_path = content_module.put_file_to_s3(
        const.S3_KEY_CONTENT_THUMBNAIL, img_file["data"], extension=extension
    )

    # DB 저장
    img_id = content_module.save_thumbnail_file_path(img_file_path, user_id, basic)

    return {"data": {
        "thumbnail_id": img_id,
        "file_path": "/" + img_file_path
    }}
