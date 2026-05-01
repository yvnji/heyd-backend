from zoneinfo import ZoneInfoNotFoundError

import const
from lib import time
from lib.decorator import mandatory_params
from lib.exception import IdolmasterBadRequestException
from lib.exception import IdolmasterResourceNotFoundExeption
from service import product as product_module


@mandatory_params(["email", "platform", "product_id"])
def post_access_product(event, context, body):
    """상품 구매창에 접근"""
    email = body["email"]
    platform = body["platform"]
    product_id = body["product_id"]

    # platform 확인
    if platform not in (
        const.PLATFORM_GOOGLE_PLAY,
        const.PLATFORM_APP_STORE,
        const.PLATFORM_PORTONE,
    ):
        raise IdolmasterResourceNotFoundExeption(message="platform not found")

    # 상품 이름 확인
    products = product_module.dict_products(platform)
    print(products)
    if product_id not in products:
        raise IdolmasterResourceNotFoundExeption(
            message="product_id not found", result_code=1
        )

    product_module.access_product(email, platform, products[product_id]["charge_type"])


@mandatory_params(["email", "platform", "product_id"])
def post_charge_product(event, context, body):
    """상품 구매를 통한 다트/젬 충전.
    현재는 내부 호출용 API(from Lambda 'purchase-api')
    """
    email = body["email"]
    product_id = body["product_id"]
    platform = body["platform"]
    product_item = product_module.dict_products(platform)[product_id]
    expiration_at = product_module.get_expiration_utc(product_item["charge_type"])
    res_charge = product_module.charge_product_expiration(
        email,
        product_item["charge_type"],
        product_item["dart"],
        product_item["gem"],
        expiration_at,
        platform=platform,
    )
    print(f"success of charge : {res_charge}")
    res = product_module.get_product(email)
    return {"data": res}


@mandatory_params(["email"])
def post_get_product(event, context, body):
    return {"data": product_module.get_product(body["email"])}


@mandatory_params(["email", "timezone_iana"])
def post_get_reward_status(event, context, body):
    reward_survey = product_module.list_product_expiration(
        body["email"], charge_type=const.PRODUCT_CHARGE_TYPE_REWARD_SURVEY
    )

    # timezone_iana 확인
    try:
        reward_daily_at = time.now(time.timezone_info(body["timezone_iana"])).replace(
            hour=23, minute=59, second=59
        )
    except ZoneInfoNotFoundError:
        raise IdolmasterBadRequestException(message="Invalid timezone_iana")

    reward_daily = product_module.list_product_expiration(
        body["email"],
        charge_type=const.PRODUCT_CHARGE_TYPE_REWARD_DAILY,
        expiration_utc=reward_daily_at,
    )
    reward_daily_at = reward_daily_at.astimezone(time.tz_utc).replace(
        microsecond=0, tzinfo=None
    )  # 비교를 위해 UTC datetime 형태로 변경

    if reward_daily and reward_daily[0]["expiration_utc"] == reward_daily_at:
        ch_daily = True
    else:
        ch_daily = False

    ch_reward_survey = True if reward_survey else False
    if ch_reward_survey:
        survey_status = const.SURVEY_STATUS_REWARDED
    else:
        ch_survey = product_module.check_survey(body["email"])
        if ch_survey:
            survey_status = const.SURVEY_STATUS_BEFORE_REWARD
        else:
            survey_status = const.SURVEY_STATUS_BEFORE_SURVEY

    return {
        "data": {
            const.PRODUCT_CHARGE_TYPE_REWARD_DAILY: ch_daily,
            const.PRODUCT_CHARGE_TYPE_REWARD_SURVEY: survey_status,
        }
    }


@mandatory_params(["email"])
def post_get_survey_link(event, context, body):
    return {"data": {"link": product_module.get_survey_link(body["email"])}}


def post_list_charge_type(event, context, body):
    return {"data": product_module.list_charge_type()}


@mandatory_params(["email", "timezone_iana"])
def post_reward_product_daily(event, context, body):
    """일일 접속보상"""
    # timezone_iana 확인
    try:
        expiration_at = product_module.get_expiration_utc(
            const.PRODUCT_CHARGE_TYPE_REWARD_DAILY, timezone_iana=body["timezone_iana"]
        )
    except ZoneInfoNotFoundError:
        raise IdolmasterBadRequestException(message="Invalid timezone_iana")

    charge_types = product_module.list_charge_type(
        name=const.PRODUCT_CHARGE_TYPE_REWARD_DAILY
    )
    if not charge_types:
        raise IdolmasterBadRequestException(message="Charge type not found")

    charge_type = charge_types[0]

    return {
        "data": product_module.charge_product_expiration(
            body["email"],
            const.PRODUCT_CHARGE_TYPE_REWARD_DAILY,
            charge_type["dart"],
            charge_type["gem"],
            expiration_at,
        )
    }


@mandatory_params(["email"])
def post_reward_product_survey(event, context, body):
    """설문 보상"""
    ret = False
    if not product_module.list_product_expiration(
        body["email"], charge_type=const.PRODUCT_CHARGE_TYPE_REWARD_SURVEY
    ):
        charge_type = product_module.list_charge_type(
            name=const.PRODUCT_CHARGE_TYPE_REWARD_SURVEY
        )[0]
        expiration_at = product_module.get_expiration_utc(
            const.PRODUCT_CHARGE_TYPE_REWARD_SURVEY
        )
        ret = product_module.charge_product_expiration(
            body["email"],
            const.PRODUCT_CHARGE_TYPE_REWARD_SURVEY,
            charge_type["dart"],
            charge_type["gem"],
            expiration_at,
        )
    return {"data": ret}


@mandatory_params(["email", "dart", "gem"])
def post_test_product(event, context, body):
    """테스트를 위한 API"""
    expiration_at = product_module.get_expiration_utc(
        const.PRODUCT_CHARGE_TYPE_PURCHASE_TEMP01
    )
    res_charge = product_module.charge_product_expiration(
        body["email"],
        const.PRODUCT_CHARGE_TYPE_PURCHASE_TEMP01,
        int(body["dart"]),
        int(body["gem"]),
        expiration_at,
    )
    print(f"success of charge : {res_charge}")
    res = product_module.get_product(body["email"])
    return {"data": res}
