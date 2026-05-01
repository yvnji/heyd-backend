import boto3
import const
import os
import time
from decimal import Decimal
from lib import invoke
from lib.http_request import request


def get_access_token() -> str:
    """포트원 인증 토큰 조회"""
    url = const.PORTONE_API_URL + const.PORTONE_API_GET_TOKEN
    headers = {"Content-Type": "application/json"}
    body = {"imp_key": const.PORTONE_KEY, "imp_secret": const.PORTONE_SECRET_KEY}
    res_token = request("POST", url, headers=headers, data=body)
    print(f"{const.PORTONE_API_GET_TOKEN} response : {res_token}")

    if not res_token["status_code"] == 200:
        raise Exception("failed to get access token")

    return res_token["response"]["response"]["access_token"]


def get_payment_data(access_token: str, imp_key: str) -> dict:
    """포트원 결제 정보 조회

    :param access_token : 포트원 인증 토큰
    :param imp_key : 포트원 결제 ID
    :return : dict (포트원 결제 내역)
    """
    url = const.PORTONE_API_URL + const.PORTONE_API_PAYMENTS + imp_key
    headers = {"Authorization": f"Bearer {access_token}"}
    res_payment = request("GET", url, headers=headers)
    print(f"payments response : {res_payment}")

    if not res_payment["status_code"] == 200:
        raise Exception("failed to get payment data")

    return res_payment["response"]["response"]


def verify_portone_payment(imp_uid: str, amount: str) -> dict:
    """포트원 결제 검증

    :param str imp_uid : 포트원거래고유번호
    :param str amount : 결제금액
    :return
        {
            'is_valid': bool,
            'payment_status': str (ready / paid / cancelled / failed)
            'error': str (검증 실패)
        }
    """
    try:
        access_token = get_access_token()
        payment_data = get_payment_data(access_token, imp_uid)
        is_valid = False
        payment_status = payment_data["status"]
        if payment_status == "paid" and str(payment_data["amount"]) == str(amount):
            is_valid = True
        return {"is_valid": is_valid, "payment_status": payment_status}

    except Exception as e:
        return {"is_valid": False, "error": f"{e}"}


def save_purchase_history_idolmaster(email: str, product_id: str, imp_uid: str) -> None:
    """Product 구매 정보를 DB에 저장"""
    api_alias = os.environ["API_ALIAS"]
    dynamodb = boto3.resource("dynamodb")
    table = (
        "idolmaster_history_purchase"
        if api_alias == const.ALIAS_PROD
        else f"{api_alias}_idolmaster_history_purchase"
    )
    purchase_table = dynamodb.Table(table)
    item = {
        "email": email,
        "created_at": round(Decimal(time.time()), 3),
        "payment_number": imp_uid,
        "platform": const.PLATFORM_PORTONE,
        "product_id": product_id,
    }
    dynamodb.put_item(purchase_table, item)


def charge_product(email, product_id):
    """Dart/Gem 충전"""
    lambda_name = "idolmaster-api"
    path = f"/public/products/{product_id}/charges"
    body = {
        "email": email,
        "platform": const.PLATFORM_PORTONE,
        "product_id": product_id,
    }
    invoke.invoke_lambda_rest_api(lambda_name, "POST", path, body)
