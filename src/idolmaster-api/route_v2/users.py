from datetime import datetime
from zoneinfo import ZoneInfoNotFoundError

import const
from lib.decorator import mandatory_params
from lib.exception import IdolmasterBadRequestException
from lib.exception import IdolmasterResourceNotFoundExeption
from service import product as product_module
from service import user as user_module


def delete_users(event, context, params):
    """회원탈퇴
    post_delete_account 수정
    """
    email = event["requestContext"]["authorizer"]["email"]
    memo = params.get("leave_memo")
    user_module.delete_account(email, memo)


def get_users(event, context, params):
    """사용자 정보 조회
    post_get_user_info 수정
    """
    email = event["requestContext"]["authorizer"]["email"]
    fcm_token = params.get("fcm_token")
    res = user_module.get_user_info(email, fcm_token)
    return {"data": res}


@mandatory_params(
    [
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
def post_users(event, context, body):
    """회원가입 시 사용자 정보 저장
    post_save_user_info 수정
    """
    email = event["requestContext"]["authorizer"]["email"]
    platform = event["requestContext"]["authorizer"]["platform"]
    name = body["name"]
    nickname = body["nickname"]
    birth = body["birth_date"]
    language = body["language"]
    agree_privacy = body["privacy_agree"]
    agree_avatar = body["avatar_agree"]
    agree_marketing = body["marketing_agree"]
    timezone_iana = body["timezone_iana"]
    gender = body.get("gender")

    # check params
    try:
        if gender and gender not in ("Male", "Female", "Non-binary"):
            raise ValueError
        gender = gender if gender else "-"
        birth = datetime.strptime(birth, "%m%d%Y").strftime("%Y-%m-%d")
        reward_time_at = product_module.get_expiration_utc(
            const.PRODUCT_CHARGE_TYPE_REWARD_DAILY,
            timezone_iana=timezone_iana
        )
    except ValueError:
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
        const.PRODUCT_CHARGE_TYPE_REWARD_DAILY
    )[0]
    product_module.charge_product_expiration(
        email,
        const.PRODUCT_CHARGE_TYPE_REWARD_DAILY,
        charge_type["dart"],
        charge_type["gem"],
        reward_time_at,
    )


def put_users(event, context, body):
    """사용자 정보 변경
    post_update_language, post_update_nickname 통합
    key 이름 변경
    """
    email = event["requestContext"]["authorizer"]["email"]
    language = body.get("language")
    nickname = body.get("nickname")

    user_module.update_user(
        email,
        language,
        nickname
    )


#######################################################
# path 시작이 /users/ 아닌 API
#######################################################


@mandatory_params(["email", "report_message"])
def post_users_blocks(event, context, body):
    """다른 사용자 블락처리
    post_block_and_report 수정
    """
    email = event["requestContext"]["authorizer"]["email"]
    blocked_email = body["creator_id"]
    report_message = body["report_message"]

    # creator_id 확인
    if not user_module.check_used_email(blocked_email):
        raise IdolmasterResourceNotFoundExeption(message="creator_id not found")

    user_module.block_and_report_creator(
        email, blocked_email, report_message
    )


@mandatory_params(["subject", "explanation"])
def post_users_reports(event, context, body):
    """신고 내용 제출
    post_send_report 수정
    """
    email = event["requestContext"]["authorizer"]["email"]
    subject = body["subject"]
    explanation = body["explanation"]
    user_module.send_report(email, subject, explanation)
