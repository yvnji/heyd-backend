from lib.decorator import mandatory_params
from lib.exception import IdolmasterBadRequestException
from lib.exception import IdolmasterConflictResourceException
from lib.exception import IdolmasterForbiddenException
from lib.exception import IdolmasterResourceNotFoundExeption
from lib.moderation import moderate_image
from lib.parser import convert_to_bool
from service import character as character_module
from service import chat as chat_module
from service import reaction as reaction_module
from thirdparty.mariadb import get_db_connection


@mandatory_params(["characters"])
def delete_characters(event, context, params):
    """내가 만든 캐릭터 삭제
    user.post_delete_my_character 수정
    """
    email = event["requestContext"]["authorizer"]["email"]
    character_id = params["characters"]

    # character_id 확인
    character = character_module.get_character(character_id)
    if not character:
        raise IdolmasterResourceNotFoundExeption(message="character_id not found")
    if not character["email"] == email:
        raise IdolmasterForbiddenException

    character_module.delete_character(character_id)


@mandatory_params(["characters", "comments"])
def delete_characters_comments(event, context, params):
    """내가 등록한 캐릭터 댓글 삭제
    character.post_delete_comment 수정
    parameter character_id -> path parameter characters
    parameter comment_id -> path parameter comments
    """
    email = event["requestContext"]["authorizer"]["email"]
    character_id = params["characters"]
    comment_id = params["comments"]
    cursor = get_db_connection().cursor()

    # character_id 확인
    if not character_module.get_character(character_id, cursor=cursor):
        raise IdolmasterResourceNotFoundExeption(message="character_id not found")

    # comment_id 확인
    comment = character_module.get_comment(
        comment_id, character_id=character_id, cursor=cursor
    )
    if not comment:
        raise IdolmasterResourceNotFoundExeption(
            message="comment_id not found", result_code=1
        )
    if not email == comment["email"]:
        raise IdolmasterForbiddenException

    character_module.delete_comment(email, comment_id, character_id)


@mandatory_params(["characters", "comments"])
def delete_characters_comments_likes(event, context, params):
    """캐릭터 댓글 좋아요 취소
    character.post_unlike_comment 수정
    parameter character_id -> path parameter characters
    parameter comment_id -> path parameter comments
    """
    email = event["requestContext"]["authorizer"]["email"]
    character_id = params["characters"]
    comment_id = params["comments"]
    cursor = get_db_connection().cursor()

    # character_id 확인
    if not character_module.get_character(character_id, cursor=cursor):
        raise IdolmasterResourceNotFoundExeption(message="character_id not found")

    # comment_id 확인
    if not character_module.get_comment(
        comment_id, character_id=character_id, cursor=cursor
    ):
        raise IdolmasterResourceNotFoundExeption(
            message="comment_id not found", result_code=1
        )

    character_module.set_unlike_comment(email, character_id, comment_id)


# TODO check using
@mandatory_params(["characters", "emojis"])
def delete_characters_emojis(event, context, params):
    """캐릭터 이모지 취소
    character.post_delete_emoji 수정
    parameter character_id -> path parameter characters
    parameter emoji_id -> path parameter emojis
    """
    email = event["requestContext"]["authorizer"]["email"]
    character_id = params["characters"]
    emoji_id = params["emojis"]
    cursor = get_db_connection().cursor()

    # character_id 확인
    if not character_module.get_character(character_id, cursor=cursor):
        raise IdolmasterResourceNotFoundExeption(message="character_id not found")

    # emoji_id 확인
    try:
        emoji_id = int(emoji_id)
    except ValueError:
        raise IdolmasterResourceNotFoundExeption(
            message="emoji_id not found", result_code=1
        )
    emoji_list = reaction_module.list_emoji(cursor=cursor)
    if emoji_id not in [e["emoji_id"] for e in emoji_list]:
        raise IdolmasterResourceNotFoundExeption(
            message="emoji_id not found", result_code=1
        )

    character_module.delete_emoji(email, character_id, emoji_id)


@mandatory_params(["characters"])
def delete_characters_likes(event, context, params):
    """캐릭터 좋아요 취소
    users.delete_character_like 수정
    """
    email = event["requestContext"]["authorizer"]["email"]
    character_id = params["characters"]

    # character_id 확인
    if not character_module.get_character(character_id):
        raise IdolmasterResourceNotFoundExeption(message="character_id not found")

    character_module.update_like_character(email, character_id, False)


def get_characters(event, context, params):
    """캐릭터 리스트 조회
    타입, 정렬기준, 캐릭터 이름 및 설명 필터 가능
    아래 API 통합
        - user.post_get_my_creation_list
        - post_get_all_list
        - post_get_all_list_popular
        - post_get_hot_list
        - post_get_explore_list
        - post_get_list_by_type
    """
    email = event["requestContext"]["authorizer"]["email"]
    character_type = params.get("type")
    creator = params.get("creator")
    search = params.get("search")
    sort_by = params.get("sort_by")

    # check type
    try:
        page = int(params.get("page", 1))
        page_size = int(params.get("page_size", 10))
        like = convert_to_bool(params.get("like", False))
        own = convert_to_bool(params.get("own", False))
        offset = (page - 1) * page_size
        if page < 1 or page_size < 1:
            raise ValueError
        if sort_by and sort_by not in ["chat", "like", "main"]:
            raise ValueError
    except ValueError:
        raise IdolmasterBadRequestException(message="Invalid params", result_code=1)

    # 본인 소유의 캐릭터만 조회
    if own:
        creator = email

    # type 확인
    if character_type and character_type not in [
        t["type"] for t in character_module.list_types()
    ]:
        raise IdolmasterBadRequestException(message="Invalid params", result_code=1)

    if sort_by == "main":
        characters = character_module.list_character_explore(email)
    else:
        characters = character_module.list_character(
            email,
            page_size=page_size,
            offset=offset,
            character_type=character_type,
            sort_by=sort_by,
            search_keyword=search,
            like=like,
            creator=creator,
        )

    return {"data": characters}


@mandatory_params(["characters"])
def get_characters_chatrooms_check(event, context, params):
    """채팅방 존재 여부 확인
    chat.post_check_chat_room_existence 수정
    """
    email = event["requestContext"]["authorizer"]["email"]
    character_id = params["characters"]
    cursor = get_db_connection().cursor()

    # character_id 확인
    if not character_module.get_character(character_id, cursor=cursor):
        raise IdolmasterResourceNotFoundExeption(message="character_id not found")

    # # premium 구독 확인
    # if (
    #     not user_module.check_premium(email)
    #     and character_module.get_character(character_id, cursor=cursor)["type"]
    #     == const.CHARACTER_TYPE_MYSTERY
    # ):
    #     raise IdolmasterBadRequestException(
    #         message="Only available for premium subscribers"
    #     )

    res = chat_module.check_chatroom(email, character_id)
    return {"data": res}


@mandatory_params(["characters"])
def get_characters_comments(event, context, params):
    """캐릭터 댓글 리스트 조회
    post_comment_list 수정
    """
    email = event["requestContext"]["authorizer"]["email"]
    character_id = params["characters"]
    sort_by = params.get("sort_by", "newest")  # "newest", "top"

    # check type
    try:
        page = int(params.get("page", 1))
        page_size = int(params.get("page_size", 10))
        offset = (page - 1) * page_size
        if page < 1 or page_size < 1:
            raise ValueError
        if sort_by and sort_by not in ["newest", "top"]:
            raise ValueError
    except ValueError:
        raise IdolmasterBadRequestException(message="Invalid params", result_code=1)

    # character_id 확인
    if not character_module.get_character(character_id):
        raise IdolmasterResourceNotFoundExeption(message="character_id not found")

    res = character_module.list_comment(email, character_id, sort_by, page_size, offset)
    return {"data": res["comments"], "total": res["total_count"]}


@mandatory_params(["characters"])
def get_characters_personas(event, context, params):
    """캐릭터 페르소나 포함 세부 정보 조회
    post_persona_details_v2 이름 변경
    """
    email = event["requestContext"]["authorizer"]["email"]
    character_id = params["characters"]

    # character_id 확인
    if not character_module.get_character(character_id):
        raise IdolmasterResourceNotFoundExeption(message="character_id not found")

    res = character_module.get_persona_details_v2(email, character_id)
    return {"data": res}


@mandatory_params(
    [
        "avatar_id",
        "character_name",
        "character_type",
        "generate_type",
        "llm_type",
        "opening",
        "persona",
        "show_persona",
    ]
)
def post_characters(event, context, body):
    """캐릭터 세부사항 저장
    post_create_character 수정
    body character_id -> avatar_id
    response character_type -> generate_type
    """
    email = event["requestContext"]["authorizer"]["email"]
    avatar_id = body["avatar_id"]
    name = body["character_name"]
    character_type = body["character_type"]
    generate_type = body["generate_type"]
    llm_type = body["llm_type"]
    first_msg = body["opening"]
    basic_info = body["persona"]
    img_file = body.get("profile_image")
    thumbnail_file_path = body.get("thumbnail_file_path")
    description = body.get("tag_line")
    cursor = get_db_connection().cursor()

    # check type
    try:
        show_persona = int(body["show_persona"])
        if show_persona not in (0, 1):
            raise ValueError
        if character_type not in [
            t["type"] for t in character_module.list_types(cursor=cursor)
        ]:
            raise ValueError
        if generate_type not in ("avaturn", "preset", "user"):
            raise ValueError
    except ValueError:
        raise IdolmasterBadRequestException(message="Invalid params", result_code=1)

    # avatar_id 확인
    if not character_module.get_avatar(avatar_id, cursor=cursor):
        raise IdolmasterResourceNotFoundExeption(message="avatar_id not found")

    # 썸네일 파일 확인
    img_file_path = None
    if img_file:
        is_censored = moderate_image(img_object=img_file["data"])
        print(f"is_censored: {is_censored}")
        if is_censored:
            raise IdolmasterBadRequestException(
                message="Inappropriate image", result_code=2
            )

        # 썸네일 파일 S3 저장
        extension = (
            img_file["filename"].split(".")[-1] if "." in img_file["filename"] else ""
        )
        img_file_path = character_module.put_thumbnail_s3(
            img_file["data"], extension=extension
        )
    else:
        img_file_path = thumbnail_file_path.strip("/") if thumbnail_file_path else None

    res = character_module.create_character(
        email,
        img_file_path,
        avatar_id,
        name,
        first_msg,
        description,
        basic_info,
        show_persona,
        generate_type,
        character_type,
        llm_type,
    )
    return {"data": res}


@mandatory_params(["characters"])
def post_characters_avatar_copies(event, context, body):
    """캐릭터의 아바타를 내 아바타 목록에도 보이도록 복사
    post_copy_avatar 수정
    """
    email = event["requestContext"]["authorizer"]["email"]
    character_id = body["characters"]

    # character_id 확인
    if not character_module.get_character(character_id):
        raise IdolmasterResourceNotFoundExeption(message="character_id not found")

    character_module.copy_avatar(email, character_id)


@mandatory_params(["characters", "report_message"])
def post_characters_reports(event, context, body):
    """캐릭터 신고 처리
    post_block_and_report 수정
    409 추가
    """
    email = event["requestContext"]["authorizer"]["email"]
    character_id = body["characters"]
    msg = body["report_message"]

    # character_id 확인
    character = character_module.get_character(character_id)
    if not character:
        raise IdolmasterResourceNotFoundExeption(message="character_id not found")
    if character["email"] == email:
        raise IdolmasterConflictResourceException(message="This is your character")

    blocked = character_module.block_and_report(email, character_id, msg)

    # 이미 신고를 했었을 경우
    if blocked:
        raise IdolmasterConflictResourceException(
            message="Already blocked", result_code=1
        )


@mandatory_params(["characters", "content"])
def post_characters_comments(event, context, body):
    """캐릭터 댓글 생성
    post_create_comment 수정
    """
    email = event["requestContext"]["authorizer"]["email"]
    character_id = body["characters"]
    content = body["content"]

    # character_id 확인
    if not character_module.get_character(character_id):
        raise IdolmasterResourceNotFoundExeption(message="character_id not found")

    character_module.create_comment(email, character_id, content)


@mandatory_params(["characters", "comments"])
def post_characters_comments_likes(event, context, body):
    """캐릭터 댓글에 좋아요 생성
    post_like_comment 이름 변경
    """
    email = event["requestContext"]["authorizer"]["email"]
    character_id = body["characters"]
    comment_id = body["comments"]
    cursor = get_db_connection().cursor()

    # character_id 확인
    if not character_module.get_character(character_id, cursor=cursor):
        raise IdolmasterResourceNotFoundExeption(message="character_id not found")

    # comment_id 확인
    if not character_module.get_comment(
        comment_id, character_id=character_id, cursor=cursor
    ):
        raise IdolmasterResourceNotFoundExeption(
            message="comment_id not found", result_code=1
        )

    character_module.set_like_comment(email, character_id, comment_id)


@mandatory_params(["characters", "emojis"])
def post_characters_emojis(event, context, body):
    """캐릭터에 이모지 등록
    post_post_emoji 수정
    """
    email = event["requestContext"]["authorizer"]["email"]
    character_id = body["characters"]
    emoji_id = body["emojis"]
    cursor = get_db_connection().cursor()

    # character_id 확인
    if not character_module.get_character(character_id, cursor=cursor):
        raise IdolmasterResourceNotFoundExeption(message="character_id not found")

    # emoji_id 확인
    try:
        emoji_id = int(emoji_id)
    except ValueError:
        raise IdolmasterResourceNotFoundExeption(
            message="emoji_id not found", result_code=1
        )
    emoji_list = reaction_module.list_emoji(cursor=cursor)
    if emoji_id not in [e["emoji_id"] for e in emoji_list]:
        raise IdolmasterResourceNotFoundExeption(
            message="emoji_id not found", result_code=1
        )

    character_module.post_emoji(email, character_id, emoji_id)


@mandatory_params(["characters"])
def post_characters_likes(event, context, body):
    """캐릭터 좋아요 등록
    users.post_character_like 수정
    """
    email = event["requestContext"]["authorizer"]["email"]
    character_id = body["characters"]

    # character_id 확인
    if not character_module.get_character(character_id):
        raise IdolmasterResourceNotFoundExeption(message="character_id not found")

    character_module.update_like_character(email, character_id, True)


@mandatory_params(
    [
        "characters",
        "character_name",
        "opening",
        "persona",
        "show_persona",
        "tag_line"
    ]
)
def put_characters(event, context, body):
    """캐릭터 수정
    edit_character 수정
    """
    character_id = body["characters"]
    name = body["character_name"]
    first_msg = body["opening"]
    basic_info = body["persona"]
    description = body["tag_line"]
    img_file = body.get("profile_image")
    avatar_id = body.get("avatar_id")
    img_file_path = ""

    # check type
    try:
        show_persona = int(body["show_persona"])
        if show_persona not in (0, 1):
            raise ValueError
    except ValueError:
        raise IdolmasterBadRequestException(message="Invalid params", result_code=1)

    # character_id 확인
    character = character_module.get_character(character_id)
    if not character:
        raise IdolmasterResourceNotFoundExeption(message="character_id not found")

    # avatar_id 확인
    if avatar_id:
        if not character_module.get_avatar(avatar_id):
            raise IdolmasterResourceNotFoundExeption(message="avatar_id not found", result_code=1)

    # 썸네일 파일 S3 저장
    if img_file:
        # 썸네일 파일 확인
        is_censored = moderate_image(img_object=img_file["data"])
        print(f"is_censored: {is_censored}")
        if is_censored:
            raise IdolmasterBadRequestException(
                message="Inappropriate image", result_code=2
            )

        extension = (
            img_file["filename"].split(".")[-1] if "." in img_file["filename"] else ""
        )
        img_file_path = character_module.put_thumbnail_s3(
            img_file["data"], extension=extension
        )

    character_module.edit_character(
        img_file_path,
        character_id,
        name,
        description if description else None,
        first_msg,
        basic_info,
        show_persona,
        avatar_id=avatar_id
    )


@mandatory_params(["characters", "comments", "content"])
def put_characters_comments(event, context, body):
    """캐릭터 댓글 수정
    post_edit_comment 수정
    """
    email = event["requestContext"]["authorizer"]["email"]
    character_id = body["characters"]
    comment_id = body["comments"]
    content = body["content"]
    cursor = get_db_connection().cursor()

    # character_id 확인
    if not character_module.get_character(character_id, cursor=cursor):
        raise IdolmasterResourceNotFoundExeption(message="character_id not found")

    # comment_id 확인
    comment = character_module.get_comment(
        comment_id, character_id=character_id, cursor=cursor
    )
    if not comment:
        raise IdolmasterResourceNotFoundExeption(
            message="comment_id not found", result_code=1
        )
    if not email == comment["email"]:
        raise IdolmasterForbiddenException

    character_module.edit_comment(email, character_id, content, comment_id)


#######################################################
# path 시작이 /characters/ 아닌 API
#######################################################


@mandatory_params(["persona"])
def get_characters_enhanced_persona(event, context, params):
    """캐릭터 디테일(페르소나)를 AI를 통해 증강"""
    persona = params["persona"]
    name = params.get("character_name")

    return {"data": character_module.get_persona_enhanced(name, persona)}


@mandatory_params(["file_type", "generate_type"])
def get_characters_pre_signed_url(event, context, params):
    """임시로 S3에 접근 가능한 URL과 타입에 따른 파일 경로 조회
    post_get_pre_signed_url 이름 변경
    """
    file_type = params["file_type"]
    generate_type = params["generate_type"]

    # generate_type 확인
    if generate_type not in ["user", "avaturn"]:
        raise IdolmasterBadRequestException(
            message="Invalid generate_type", result_code=1
        )

    res = character_module.get_pre_signed_url(file_type, generate_type)
    return {"data": res}


@mandatory_params(["file_path"])
def get_characters_signed_url(event, context, params):
    """임시 CDN URL과 타입에 따른 파일 경로 조회"""
    file_path = params["file_path"]
    res = character_module.get_signed_url(file_path)
    return {"data": {"signed_url": res}}
