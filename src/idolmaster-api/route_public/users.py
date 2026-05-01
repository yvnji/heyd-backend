from datetime import datetime
from zoneinfo import ZoneInfoNotFoundError

import const
from lib.decorator import mandatory_params
from lib.exception import IdolmasterBadRequestException
from service import product as product_module
from service import user as user_module


@mandatory_params(["email"])
def get_users_check_email(event, context, params):
    """이메일 주소가 사용 가능한지 확인
    user.post_check_email 수정
    return 수정
    """
    email = params["email"]
    res = user_module.check_used_email(email)
    return {"data": {"used": res}}


@mandatory_params(["name"])
def get_users_check_name(event, context, params):
    """사용자 이름이 사용 가능한지 확인
    user.post_check_username 수정
    parameter username -> name
    return 수정
    """
    name = params["name"]
    res = user_module.check_used_name(name)
    return {"data": {"used": res}}


@mandatory_params(["nickname"])
def get_users_check_nickname(event, context, params):
    """닉네임으로 사용 가능한지 확인"""
    nickname = params["nickname"]
    return {"data": user_module.check_nickname(nickname)}


@mandatory_params(
    [
        "email",
        "platform",
        # "name",
        "nickname",
        # "language",
        # "birth_date",
        "privacy_agree",
        "avatar_agree",
        "marketing_agree",
        "timezone_iana",
    ]
)
def post_users(event, context, body):
    """회원가입 시 사용자 정보 저장
    post_save_user_info 수정
    """
    email = body["email"]
    platform = body["platform"]
    nickname = body["nickname"]
    agree_privacy = body["privacy_agree"]
    agree_avatar = body["avatar_agree"]
    agree_marketing = body["marketing_agree"]
    timezone_iana = body["timezone_iana"]
    gender = body.get("gender")

    name = body.get("name")
    birth = body.get("birth_date")
    language = body.get("language")

    name = name if name else None
    birth = birth if birth else None
    language = language if language else None

    # check params
    try:
        if gender and gender not in ("Male", "Female", "Non-binary"):
            raise ValueError
        if birth:
            birth = datetime.strptime(birth, "%m%d%Y").strftime("%Y-%m-%d")
        gender = gender if gender else "-"
        reward_time_at = product_module.get_expiration_utc(
            const.PRODUCT_CHARGE_TYPE_SIGN_UP,
            timezone_iana=timezone_iana
        )
        assert user_module.check_nickname(nickname)["possibility"]
    except (ValueError, AssertionError):
        raise IdolmasterBadRequestException(
            message="Invalid params",
            result_code=1
        )
    except ZoneInfoNotFoundError:
        raise IdolmasterBadRequestException(
            message="Invalid IANA",
            result_code=2
        )

    # 회원가입 정보 저장
    user_module.save_user_info(
        email,
        platform,
        name,  # account name
        nickname,
        gender,
        birth,
        language,
        agree_privacy,
        agree_avatar,
        agree_marketing,
    )

    # 회원가입 다트/젬 충전 (일일 보상)
    charge_type = product_module.list_charge_type(
        const.PRODUCT_CHARGE_TYPE_SIGN_UP
    )[0]
    product_module.charge_product_expiration(
        email,
        const.PRODUCT_CHARGE_TYPE_SIGN_UP,
        charge_type["dart"],
        charge_type["gem"],
        reward_time_at,
    )
