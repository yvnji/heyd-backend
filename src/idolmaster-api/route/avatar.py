from lib.decorator import mandatory_params
from service import avatar as avatar_module


@mandatory_params(["avatar_id"])
def post_create_export(event, context, body):
    res = avatar_module.create_export(body["avatar_id"])
    return {
        "result": 1 if res else 0,
        "data": res
    }


def post_create_user(event, context, body):
    res = avatar_module.create_user()
    return {
        "result": 1 if res else 0,
        "data": res
    }


@mandatory_params(["user_id"])
def post_delete_user(event, context, body):
    res = avatar_module.delete_user(body["user_id"])
    return {"result": 0 if res else 1}


@mandatory_params(["avatar_id", "user_id"])
def post_delete_user_avatar(event, context, body):
    res = avatar_module.delete_user_avatar(body["avatar_id"], body["user_id"])
    return {"result": 0 if res else 1}


@mandatory_params(["id"])
def post_get_customization(event, context, body):
    res = avatar_module.get_customication(body["id"])
    return {
        "result": 1 if res else 0,
        "data": res
    }


@mandatory_params(["user_id"])
def post_list_user_avatars(event, context, body):
    res = avatar_module.list_user_avatars(body["user_id"])
    return {
        "result": 1 if res else 0,
        "data": res
    }


@mandatory_params(
    ["user_id", "gender", "image_frontal"]
)
def post_new_avatar(event, context, body):
    res = avatar_module.new_avatar(
        body["user_id"],
        body["gender"],
        body["image_frontal"],
        # body["image_side_1"],
        # body["image_side_2"],
    )
    return {
        "result": 1 if res else 0,
        "data": res
    }


@mandatory_params(["user_id"])
def post_new_session(event, context, body):
    res = avatar_module.new_session(body["user_id"])
    return {
        "result": 1 if res else 0,
        "data": res
    }


@mandatory_params(["avatar_id"])
def post_render_user_avatar_async(event, context, body):
    res = avatar_module.render_user_avatar_async(body["avatar_id"])
    return {
        "result": 1 if res else 0,
        "data": res
    }
