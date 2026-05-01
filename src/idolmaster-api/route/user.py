import json
from datetime import datetime

import const
from lib.decorator import mandatory_params
from lib.exception import IdolmasterForbiddenException
from lib.exception import IdolmasterResourceNotFoundExeption
from service import character as character_module
from service import product as product_module
from service import user as user_module


def delete_character_like(event, context, params):
    params = json.loads(event["body"])
    character_module.update_like_character(
        params["email"], params["character_id"], False
    )
    return {"result": 1}


@mandatory_params(["email", "creator_id", "report_message"])
def post_block_and_report(event, context, body):
    # creator_id 확인
    if not user_module.check_used_email(body["creator_id"]):
        raise IdolmasterResourceNotFoundExeption(message="creator_id not found")

    return user_module.block_and_report_creator(
        body["email"], body["creator_id"], body["report_message"]
    )


@mandatory_params(["email", "character_id"])
def post_character_like(event, context, body):
    # character_id 확인
    if not character_module.get_character(body["character_id"]):
        raise IdolmasterResourceNotFoundExeption(message="character_id not found")

    character_module.update_like_character(body["email"], body["character_id"], True)
    return {"result": 1}


@mandatory_params(["email"])
def post_check_email(event, context, body):
    res = user_module.check_used_email(body["email"])
    return {"result": 0 if res else 1}


@mandatory_params(["username"])
def post_check_username(event, context, body):
    res = user_module.check_used_name(body["username"])
    return {"result": 0 if res else 1}


@mandatory_params(["email", "leave_memo"])
def post_delete_account(event, context, body):
    user_module.delete_account(body["email"], body["leave_memo"])


@mandatory_params(["email", "character_id"])
def post_delete_my_character(event, context, body):
    # character_id 확인
    character = character_module.get_character(body["character_id"])
    if not character:
        raise IdolmasterResourceNotFoundExeption(message="character_id not found")
    if not character["email"] == body["email"]:
        raise IdolmasterForbiddenException

    character_module.delete_character(body["character_id"])


@mandatory_params(["email"])
def post_get_my_creation_list(event, context, body):
    return user_module.list_creation_character(body["email"])


@mandatory_params(["email"])
def post_get_my_favorite_list(event, context, body):
    return user_module.list_favorite_character(body["email"])


# @mandatory_params(["email"])
# def post_get_premium(event, context, body):
#     """초거대 사업을 위한 임시 api. (프리미엄 구독 확인)"""
#     return {"premium": user_module.check_premium(body["email"])}


@mandatory_params(["email", "fcm_token"])
def post_get_user_info(event, context, body):
    res = user_module.get_user_info(body["email"], body["fcm_token"])
    if res:
        del res["premium"]
        return {
            "result": 1,
            "data": res
        }
    else:
        return {
            "result": 0,
            "message": "Not Authorized"
        }


@mandatory_params(["email"])
def post_save_login_history(event, context, body):
    user_ip = event["headers"].get("X-Forwarded-For", "").split(",")[0].strip()
    user_module.save_login_history(body["email"], user_ip)


@mandatory_params(
    [
        "email",
        "name",
        "nickname",
        "language",
        "birth_date",
        "privacy_agree",
        "avatar_agree",
        "marketing_agree",
        "timezone_iana",
    ]
)
def post_save_user_info(event, context, body):
    gender = body.get("gender")
    gender = gender if gender else "-"
    platform = user_module.get_platform_v1(body["email"])

    # 회원가입 정보 저장
    user_module.save_user_info(
        body["email"],
        platform,
        body["name"],  # account name
        body["nickname"],
        gender,
        datetime.strptime(body["birth_date"], "%m%d%Y").strftime("%Y-%m-%d"),
        body["language"],
        body["privacy_agree"],
        body["avatar_agree"],
        body["marketing_agree"],
    )

    # 회원가입 다트/젬 충전 (일일 보상)
    charge_type = product_module.list_charge_type(
        const.PRODUCT_CHARGE_TYPE_REWARD_DAILY
    )[0]
    expiration_at = product_module.get_expiration_utc(
        const.PRODUCT_CHARGE_TYPE_REWARD_DAILY,
        timezone_iana=body["timezone_iana"]
    )
    product_module.charge_product_expiration(
        body["email"],
        const.PRODUCT_CHARGE_TYPE_REWARD_DAILY,
        charge_type["dart"],
        charge_type["gem"],
        expiration_at
    )


@mandatory_params(["email", "subject", "explanation"])
def post_send_report(event, context, body):
    user_module.send_report(body["email"], body["subject"], body["explanation"])


# @mandatory_params(["email"])
# def post_subscribe_premium(event, context, body):
#     """초거대 사업을 위한 임시 api. (프리미엄 구독 신청)"""
#     user_module.subscribe_premium(body["email"])


@mandatory_params(["email", "new_language"])
def post_update_language(event, context, body):
    return user_module.update_language(body["email"], body["new_language"])


@mandatory_params(["email", "new_nickname"])
def post_update_nickname(event, context, body):
    return user_module.update_nickname(body["email"], body["new_nickname"])


# @mandatory_params(["email"])
# def post_unsubscribe_premium(event, context, body):
#     """초거대 사업을 위한 임시 api. (프리미엄 구독 취소)"""
#     user_module.unsubscribe_premium(body["email"])
