from lib.decorator import mandatory_params
from service import avatar as avatar_module
from service import character as character_module


@mandatory_params(["avatar_id", "user_id"])
def delete_avaturn_avatars(event, context, params):
    """POST /avatar/deleteUserAvatar 수정"""
    avatar_module.delete_user_avatar(params["avatar_id"], params["user_id"])


@mandatory_params(["user_id"])
def delete_avaturn_users(event, context, params):
    """POST /avatar/deleteUser 수정"""
    avatar_module.delete_user(params["user_id"])


@mandatory_params(["user_id"])
def get_avaturn_avatars(event, context, params):
    """POST /avatar/listUserAvatars 수정"""
    res = avatar_module.list_user_avatars(params["user_id"])
    return {"data": res}


@mandatory_params(["avatar_id"])
def get_avaturn_customization(event, context, params):
    """POST /avatar/getCustomization 수정
    parameter id -> avatar_id 수정 (avatar_id 이름이 맞는지 확인 안해봄)
    """
    res = avatar_module.get_customication(params["custom_id"])
    return {"data": res}


def get_avaturn_user_id(event, context, params):
    """아바턴 사용자 ID 조회
    없을 경우 생성해서 DB에 저장 후 리턴
    character.post_get_avaturn_user_id 이름 변경
    """
    email = event["requestContext"]["authorizer"]["email"]
    return {
        "data": {
            "avaturn_user_id": character_module.get_avaturn_user_id(email)
        }
    }


@mandatory_params(
    ["user_id", "gender", "image_frontal"]
)
def post_avaturn_avatars(event, context, body):
    """POST /avatar/newAvatar 수정"""
    res = avatar_module.new_avatar(
        body["user_id"],
        body["gender"],
        body["image_frontal"],
        # body["image_side_1"],
        # body["image_side_2"],
    )
    return {"data": res}


@mandatory_params(["avatar_id"])
def post_avaturn_avatars_render(event, context, body):
    """POST /avatar/renderUserAvatarAsync 수정"""
    res = avatar_module.render_user_avatar_async(body["avatar_id"])
    return {"data": res}


@mandatory_params(["avatar_id"])
def post_avaturn_exports(event, context, body):
    """POST /avatar/createExport 수정"""
    res = avatar_module.create_export(body["avatar_id"])
    return {"data": res}


@mandatory_params(["user_id"])
def post_avaturn_sessions(event, context, body):
    """POST /avatar/newSession 수정"""
    res = avatar_module.new_session(body["user_id"])
    return {"data": res}


def post_avaturn_users(event, context, body):
    """POST /avatar/createUser 수정"""
    res = avatar_module.create_user()
    return {"data": res}
