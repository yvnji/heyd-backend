from zoneinfo import ZoneInfoNotFoundError

import const
from lib import time
from lib.decorator import mandatory_params
from lib.exception import IdolmasterBadRequestException
from lib.exception import IdolmasterConflictResourceException
from service import product as product_module


@mandatory_params(["timezone_iana"])
def get_rewards(event, context, params):
    """사용자의 현재 보상 상태 조회
    post_get_reward_status 수정
    """
    email = event["requestContext"]["authorizer"]["email"]
    timezone_iana = params["timezone_iana"]
    reward_survey = product_module.list_product_expiration(
        email, charge_type=const.PRODUCT_CHARGE_TYPE_REWARD_SURVEY
    )

    # timezone_iana 확인
    try:
        reward_daily_at = time.now(time.timezone_info(timezone_iana)).replace(
            hour=23, minute=59, second=59
        )
    except ZoneInfoNotFoundError:
        raise IdolmasterBadRequestException(
            message="Invalid params",
            result_code=1)

    reward_daily = product_module.list_product_expiration(
        email,
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
        ch_survey = product_module.check_survey(email)
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


@mandatory_params(["type"])
def post_rewards(event, context, body):
    """사용자 보상 제공
    post_reward_product_daily, post_reward_product_survey 통합
    return 값 변경
    exception 400(Invalid path), 409 추가
    """
    email = event["requestContext"]["authorizer"]["email"]
    reward_type = body["type"]
    timezone_iana = body.get("timezone_iana")
    reward_charge_type = None
    expiration_at = None

    if reward_type == "daily":
        reward_charge_type = const.PRODUCT_CHARGE_TYPE_REWARD_DAILY

        # timezone_iana 확인
        try:
            # if not timezone_iana:
            #     raise IdolmasterBadRequestException(message="Lost parameters : timezone_iana")
            expiration_at = product_module.get_expiration_utc(
                reward_charge_type,
                timezone_iana=timezone_iana
            )
        except ZoneInfoNotFoundError:
            raise IdolmasterBadRequestException(
                message="Invalid params",
                result_code=1)

        # 중복 확인
        if product_module.list_product_expiration(
            email, charge_type=reward_charge_type, expiration_utc=expiration_at
        ):
            raise IdolmasterConflictResourceException

    elif reward_type == "survey":
        reward_charge_type = const.PRODUCT_CHARGE_TYPE_REWARD_SURVEY
        expiration_at = product_module.get_expiration_utc(reward_charge_type)

        # 중복 확인
        if product_module.list_product_expiration(
            email, charge_type=reward_charge_type
        ):
            raise IdolmasterConflictResourceException

    else:
        raise IdolmasterBadRequestException(
            message="Invalid params",
            result_code=1)

    charge_type = product_module.list_charge_type(
        name=reward_charge_type
    )[0]
    res = product_module.charge_product_expiration(
        email,
        reward_charge_type,
        charge_type["dart"],
        charge_type["gem"],
        expiration_at,
    )

    # 중복 보상 확인 실패
    if not res:
        raise Exception
