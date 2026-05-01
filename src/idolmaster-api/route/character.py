import json

from lib.decorator import mandatory_params
from lib.exception import IdolmasterBadRequestException
from lib.exception import IdolmasterConflictResourceException
from lib.exception import IdolmasterForbiddenException
from lib.exception import IdolmasterResourceNotFoundExeption
from lib.moderation import moderate_image
from service import avatar as avatar_module
from service import character as character_module
from service import reaction as reaction_module
from thirdparty.mariadb import get_db_connection


def delete_delete_avatar(event, context, params):
    params = json.loads(event["body"])
    email = params["email"]
    avaturn_id = params["avaturn_id"]

    # avaturn_id 확인
    if not character_module.get_avatar(avaturn_id, email=email):
        raise IdolmasterResourceNotFoundExeption(message="avaturn_id not found")

    character_module.delete_avatar(avaturn_id)
    return {"result": 1}


# def get_asset_avatar_list(event, context, params):
#     return character_module.list_avatar_asset()


# def get_asset_motion_list(event, context, params):
#     return character_module.list_avatar_store_motion()


# TODO check using
def get_persona_details(event, context, params):
    params = json.loads(event["body"])
    email = params["email"]
    character_id = params["character_id"]

    # character_id 확인
    if not character_module.get_character(character_id):
        raise IdolmasterResourceNotFoundExeption(message="character_id not found")

    return {
        "result": 1,
        "data": character_module.get_persona_details(email, character_id),
    }


# @mandatory_params(['id', 'type'])
# def post_asset_file_url(event, context, body):
#     return character_module.get_asset_store_character_motion_url(body['id'], body['type'])


@mandatory_params(["email", "character_id", "report_message"])
def post_block_and_report(event, context, body):

    # character_id 확인
    if not character_module.get_character(body["character_id"]):
        raise IdolmasterResourceNotFoundExeption(message="character_id not found")

    blocked = character_module.block_and_report(
        body["email"], body["character_id"], body["report_message"]
    )
    if blocked:
        msg = "This character has been already blocked and reported."
    else:
        msg = "Character has been successfully blocked and reported."

    return {"result": 1, "message": msg}


@mandatory_params(["email", "character_id"])
def post_comment_list(event, context, body):
    params = event["queryStringParameters"]
    params = params if params else {}
    sort_by = params.get("sort_by", "newest")  # "newest", "top"
    page = int(params.get("page", 1))
    page_size = int(params.get("page_size", 10))
    offset = (page - 1) * page_size

    # character_id 확인
    if not character_module.get_character(body["character_id"]):
        raise IdolmasterResourceNotFoundExeption(message="character_id not found")

    res = character_module.list_comment(
        body["email"], body["character_id"], sort_by, page_size, offset
    )
    return {"result": 1, "data": res["comments"], "total": res["total_count"]}


@mandatory_params(["email", "character_id"])
def post_copy_avatar(event, context, body):
    # character_id 확인
    if not character_module.get_character(body["character_id"]):
        raise IdolmasterResourceNotFoundExeption(message="character_id not found")

    character_module.copy_avatar(body["email"], body["character_id"])
    return {"result": 1}


@mandatory_params(
    [
        "email",
        "profile_image",
        "character_id",
        "character_name",
        "opening",
        "tag_line",
        "persona",
        "show_persona",
        "generate_type",
        "character_type",
        "llm_type",
    ]
)
def post_create_character(event, context, body):
    cursor = get_db_connection().cursor()

    # avatar_id(character_id) 확인
    if not character_module.get_avatar(body["character_id"], cursor=cursor):
        raise IdolmasterResourceNotFoundExeption(
            message="character_id(avatar_id) not found"
        )

    # character_type 확인
    if body["character_type"] not in [
        t["type"] for t in character_module.list_types(cursor=cursor)
    ]:
        raise IdolmasterBadRequestException(message="Invalid character_type")

    # 썸네일 파일 S3 저장
    img_file = body["profile_image"]
    extension = (
        img_file["filename"].split(".")[-1] if "." in img_file["filename"] else ""
    )
    img_file_path = character_module.put_thumbnail_s3(
        img_file["data"], extension=extension
    )

    # 썸네일 파일 확인
    is_censored = moderate_image(s3_path=img_file_path)
    print(f"is_censored: {is_censored}")
    if is_censored > 0:
        return {"result": 0, "message": "Inappropriate image"}

    res = character_module.create_character(
        body["email"],
        img_file_path,
        body["character_id"],
        body["character_name"],
        body["opening"],
        body["tag_line"],
        body["persona"],
        int(body["show_persona"]),
        body["generate_type"],
        body["character_type"],
        body["llm_type"],
    )
    res["character_type"] = res["generate_type"]
    del res["generate_type"]
    return {"result": 1, "data": res}


@mandatory_params(["email", "character_id", "content"])
def post_create_comment(event, context, body):
    # character_id 확인
    if not character_module.get_character(body["character_id"]):
        raise IdolmasterResourceNotFoundExeption(message="character_id not found ")

    character_module.create_comment(
        body["email"], body["character_id"], body["content"]
    )
    return {"result": 1}


@mandatory_params(["email", "comment_id", "character_id"])
def post_delete_comment(event, context, body):
    cursor = get_db_connection().cursor()

    # character_id 확인
    if not character_module.get_character(body["character_id"], cursor=cursor):
        raise IdolmasterResourceNotFoundExeption(message="character_id not found")

    # comment_id 확인
    comment = character_module.get_comment(
        body["comment_id"], character_id=body["character_id"], cursor=cursor
    )
    if not comment:
        raise IdolmasterResourceNotFoundExeption(message="comment_id not found")
    if not body["email"] == comment["email"]:
        raise IdolmasterForbiddenException

    character_module.delete_comment(
        body["email"], body["comment_id"], body["character_id"]
    )
    return {"result": 1}


# TODO check using
@mandatory_params(["email", "character_id", "emoji_id"])
def post_delete_emoji(event, context, body):
    cursor = get_db_connection().cursor()

    # character_id 확인
    if not character_module.get_character(body["character_id"], cursor=cursor):
        raise IdolmasterResourceNotFoundExeption(message="character_id not found")

    # emoji_id 확인
    emoji_list = reaction_module.list_emoji(cursor=cursor)
    if body["emoji_id"] not in [e["emoji_id"] for e in emoji_list]:
        raise IdolmasterResourceNotFoundExeption(message="emoji_id not found")

    character_module.delete_emoji(body["email"], body["character_id"], body["emoji_id"])
    return {"result": 1}


@mandatory_params(
    [
        "profile_image",
        "character_id",
        "character_name",
        "opening",
        "tag_line",
        "persona",
        "show_persona",
    ]
)
def post_edit_character(event, context, body):
    # character_id 확인
    character = character_module.get_character(body["character_id"])
    if not character:
        raise IdolmasterResourceNotFoundExeption(message="character_id not found")

    # 썸네일 파일 S3 저장
    img_file_path = ""
    if body.get("profile_image"):
        img_file = body["profile_image"]
        extension = (
            img_file["filename"].split(".")[-1] if "." in img_file["filename"] else ""
        )
        img_file_path = character_module.put_thumbnail_s3(
            img_file["data"], extension=extension
        )

        # 썸네일 파일 확인
        is_censored = moderate_image(s3_path=img_file_path)
        print(f"is_censored: {is_censored}")
        if is_censored:
            return {"result": 0, "message": "Inappropriate image"}

    character_module.edit_character(
        img_file_path,
        body["character_id"],
        body["character_name"],
        body["tag_line"] if body["tag_line"] else None,
        body["opening"],
        body["persona"],
        body["show_persona"]
    )
    return {"result": 1}


@mandatory_params(["email", "character_id", "content", "comment_id"])
def post_edit_comment(event, context, body):
    cursor = get_db_connection().cursor()

    # character_id 확인
    if not character_module.get_character(body["character_id"], cursor=cursor):
        raise IdolmasterResourceNotFoundExeption(message="character_id not found")

    # comment_id 확인
    comment = character_module.get_comment(
        body["comment_id"], character_id=body["character_id"], cursor=cursor
    )
    if not comment:
        raise IdolmasterResourceNotFoundExeption(message="comment_id not found")
    if not body["email"] == comment["email"]:
        raise IdolmasterForbiddenException

    character_module.edit_comment(
        body["email"], body["character_id"], body["content"], body["comment_id"]
    )
    return {"result": 1}


@mandatory_params(["email"])
def post_get_all_list(event, context, body):
    params = event["queryStringParameters"]
    params = params if params else {}
    page = int(params.get("page", 1))
    page_size = int(params.get("page_size", 10))
    offset = (page - 1) * page_size
    search_keyword = params.get("search", "")
    res = character_module.list_character(
        body["email"], page_size, offset, search_keyword=search_keyword
    )
    return {"result": 1, "data": res}


@mandatory_params(["email"])
def post_get_all_list_popular(event, context, body):
    params = event["queryStringParameters"]
    params = params if params else {}
    page = int(params.get("page", 1))
    page_size = int(params.get("page_size", 10))
    offset = (page - 1) * page_size
    res = character_module.list_character(
        body["email"], page_size, offset, sort_by="like"
    )
    return {"result": 1, "data": res}


@mandatory_params(["email"])
def post_get_avatar(event, context, body):
    return character_module.list_avatar_by_email(body["email"])


@mandatory_params(["email"])
def post_get_avaturn_user_id(event, context, body):
    res = character_module.get_avaturn_user_id(body["email"])
    return {"result": 1, "data": res} if res else {"result": 0}


@mandatory_params(["email"])
def post_get_celeb_list(event, context, body):
    res = character_module.list_character(body["email"], character_type="celeb")
    return {"result": 1, "data": res}


@mandatory_params(["email", "character_id"])
def post_get_details(event, context, body):
    # character_id 확인
    if not character_module.get_character(body["character_id"]):
        raise IdolmasterResourceNotFoundExeption(message="character_id not found")

    return character_module.get_character_details(body["email"], body["character_id"])


@mandatory_params(["email"])
def post_get_explore_list(event, context, body):
    res = character_module.list_character_explore(body["email"])
    return {"result": 1, "data": res}


@mandatory_params(["email"])
def post_get_hot_list(event, context, body):
    return character_module.list_character_hot(body["email"])


# TODO check using
@mandatory_params(["email", "type"])
def post_get_list_by_type(event, context, body):
    # type 확인
    if body["type"] not in [t["type"] for t in character_module.list_types()]:
        raise IdolmasterBadRequestException(message="Invalid type")

    return character_module.list_character_type(body["email"], body["type"])


@mandatory_params(["file_type", "generate_type"])
def post_get_pre_signed_url(event, context, body):
    res = character_module.get_pre_signed_url(body["file_type"], body["generate_type"])
    return {"result": 1, "data": res}


@mandatory_params(["email", "character_id", "comment_id"])
def post_like_comment(event, context, body):
    cursor = get_db_connection().cursor()

    # character_id 확인
    if not character_module.get_character(body["character_id"], cursor=cursor):
        raise IdolmasterResourceNotFoundExeption(message="character_id not found")

    # comment_id 확인
    if not character_module.get_comment(
        body["comment_id"], character_id=body["character_id"], cursor=cursor
    ):
        raise IdolmasterResourceNotFoundExeption(message="comment_id not found")

    character_module.set_like_comment(
        body["email"], body["character_id"], body["comment_id"]
    )
    return {"result": 1}


@mandatory_params(["email"])
def post_list_avatar(event, context, body):
    """아바타 타입 별 리스트 조회"""
    return {
        "data": character_module.list_avatar(
            email=body["email"], avatar_type=body.get("type")
        )
    }


@mandatory_params(["email", "character_id"])
def post_persona_details_v2(event, context, body):
    # character_id 확인
    if not character_module.get_character(body["character_id"]):
        raise IdolmasterResourceNotFoundExeption(message="character_id not found")

    res = character_module.get_persona_details_v2(body["email"], body["character_id"])
    return {"result": 1, "data": res}


# TODO check using
@mandatory_params(["email", "character_id", "emoji_id"])
def post_post_emoji(event, context, body):
    cursor = get_db_connection().cursor()

    # character_id 확인
    if not character_module.get_character(body["character_id"], cursor=cursor):
        raise IdolmasterResourceNotFoundExeption(message="character_id not found")

    # emoji_id 확인
    emoji_list = reaction_module.list_emoji(cursor=cursor)
    if body["emoji_id"] not in [e["emoji_id"] for e in emoji_list]:
        raise IdolmasterResourceNotFoundExeption(message="emoji_id not found")

    character_module.post_emoji(body["email"], body["character_id"], body["emoji_id"])
    return {"result": 1}


@mandatory_params(
    ["email", "avaturn_id", "model_file_path", "thumbnail_file", "gender"]
)
def post_save_avatar(event, context, body):
    img_file = body.get("thumbnail_file")
    img_file_path = ""

    # avaturn_id 확인
    if character_module.get_avatar(body["avaturn_id"]):
        raise IdolmasterConflictResourceException("Conflict avaturn_id")

    # 썸네일 파일 저장
    if img_file:
        img_file_path = character_module.put_thumbnail_s3(img_file["data"])

    res = avatar_module.render_user_avatar_async(body["avaturn_id"])
    print("render complete", res)
    character_module.save_avatar(
        body["email"],
        body["avaturn_id"],
        body["model_file_path"],
        img_file_path,
        body["gender"],
    )


@mandatory_params(["email", "character_id", "comment_id"])
def post_unlike_comment(event, context, body):
    cursor = get_db_connection().cursor()

    # character_id 확인
    if not character_module.get_character(body["character_id"], cursor=cursor):
        raise IdolmasterResourceNotFoundExeption(message="character_id not found")

    # comment_id 확인
    if not character_module.get_comment(
        body["comment_id"], character_id=body["character_id"], cursor=cursor
    ):
        raise IdolmasterResourceNotFoundExeption(message="comment_id not found")

    return character_module.set_unlike_comment(
        body["email"], body["character_id"], body["comment_id"]
    )
