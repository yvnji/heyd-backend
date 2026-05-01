import boto3
import const
import json
import time
import os
import uuid
from datetime import datetime
from decimal import Decimal
from lib import invoke
from oauth2client.service_account import ServiceAccountCredentials
from googleapiclient.discovery import build
from httplib2 import Http
from urllib.request import Request, urlopen


def verify_receipt(platform, receipt):
    is_valid = False
    data = None
    is_test = None

    # receipt가 문자열인 경우 JSON 파싱
    if isinstance(receipt, str):
        receipt = json.loads(receipt)

    print("receipt: ", receipt)
    print("platform: ", platform)

    # verificationData 검출
    verification_data = receipt.get("purchaseDetails", {}).get("verificationData")
    if not verification_data:
        verification_data = receipt.get("verificationData")

    if verification_data:
        if platform == const.PLATFORM_GOOGLE_PLAY:
            verification_result = verify_android_purchase(verification_data)
        elif platform == const.PLATFORM_APP_STORE:
            verification_result = verify_ios_purchase(verification_data)
        else:
            print("‼️Error: Unsupported platform")
            return {
                "is_valid": False,
                "data": data,
                "is_test": is_test,
            }

        if verification_result["is_valid"]:
            is_valid = True
            data = verification_result.get("purchase_data", {})
            is_test = verification_result.get("is_test")
        else:
            is_valid = False

    return {
        "is_valid": is_valid,
        "data": data,
        "is_test": is_test,
    }


def verify_android_purchase(verification_data):
    """안드로이드 구매 영수증 검증"""
    try:
        # androidpublisher
        scopes = [const.ANDROID_DEVELOPER_API_URL]
        credentials = ServiceAccountCredentials.from_json_keyfile_dict(
            json.loads(get_android_publisher_key()), scopes
        )
        http_auth = credentials.authorize(Http())
        androidpublisher = build(
            const.ANDROID_DEVELOPER_API,
            const.ANDROID_DEVELOPER_API_VERSION,
            http=http_auth,
        )
        # 영수증 데이터 추출
        product_id = verification_data["localVerificationData"]["productId"]
        package_name = verification_data["localVerificationData"]["packageName"]
        purchase_token = verification_data["localVerificationData"]["purchaseToken"]

        purchase_data = (
            androidpublisher.purchases()
            .products()
            .get(packageName=package_name, productId=product_id, token=purchase_token)
            .execute()
        )

        print(f"purchase_data : {purchase_data}")

        # 구매 상태 확인 (0: 구매됨, 1: 취소됨, 2: 보류 중)
        purchase_state = purchase_data.get("purchaseState")
        if purchase_state == 0:
            is_valid = True
        else:
            is_valid = False

        # 테스트 구매 여부 확인 - 검증결과 데이터에 purchaseType가 있고 해당 값이 0이라면 테스트
        # 출처: https://developers.google.com/android-publisher/api-ref/rest/v3/purchases.products?hl=ko#ProductPurchase
        is_test = purchase_data.get("purchaseType") == 0

        print(f"Android purchase verification - Product: {product_id}")
        print(f"Purchase state: {purchase_state}, Is test: {is_test}")

        return {
            "is_valid": is_valid,
            "purchase_data": purchase_data,
            "is_test": is_test,
        }

    # purchase_data: {
    #     'purchaseTimeMillis': '1727337961570',
    #     'purchaseState': 0,  # 0 이면 구매 된 것, 1이면 실패
    #     'consumptionState': 1, # 0 이면 아직 consume이 되지 않았고, 1이면 consumed된 것
    #     'developerPayload': '',
    #     'orderId': 'GPA.3398-1632-3642-59592',
    #     'purchaseType': 0, # 테스트 결제라면
    #     'acknowledgementState': 1,
    #     'kind': 'androidpublisher#productPurchase',
    #     'regionCode': 'KR'
    # }

    except Exception as e:
        error_message = str(e)
        print(f"Android verification error: {error_message}")
        return {
            "is_valid": False,
            "error": f"Verification error: {error_message}",
        }


def verify_ios_purchase(verification_data):
    """iOS 구매 영수증 검증"""
    try:
        server_verification_data = verification_data["serverVerificationData"]
        request_data = json.dumps(
            {
                "receipt-data": server_verification_data,
                # 'password': os.environ.get('SHARED_SECRET')  # If you're using a shared secret
            }
        ).encode("utf-8")

        # Apple verification URLs
        PRODUCTION_URL = const.IOS_VERIFICATION_API_URL_PRODUCTION
        SANDBOX_URL = const.IOS_VERIFICATION_API_URL_SANDBOX

        req = Request(
            PRODUCTION_URL,
            request_data,
            {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type,",
                "Access-Control-Allow-Methods": "OPTIONS,POST,GET,DELETE,PUT",
                "Content-Type": "application/json",
            },
        )
        response = json.loads(urlopen(req).read().decode("utf-8"))

        response_status = response.get("status")
        print(f"iOS 영수증 검증 결과 상태코드: {response_status}")
        # 0 - 영수증 값이 유효할 때
        # 21000 - App Store에 대한 요청이 HTTP POST 요청 방법을 사용하지 않았을 때.
        # 21001 - App Store가 더 이상 이 상태 코드를 전송하지 않을 때.
        # 21002 - receipt-data 속성의 데이터가 잘못되었거나 서비스에 일시적인 문제가 발생했을 때. 다시 시도.
        # 21003 - 시스템에서 영수증을 인증할 수 없을 때.
        # 21004 - 제공한 공유 비밀이 내 계정에 등록된 공유 비밀과 일치하지 않을 때.
        # 21005 - 영수증 서버가 일시적으로 영수증을 제공할 수 없을 때. 다시 시도.
        # 21006 - 이 영수증은 유효하지만 구독이 만료된 상태. 서버가 이 상태 코드를 수신하면 시스템은 또한 응답의 일부로 영수증 데이터를 디코딩하여 반환함. 이 상태는 자동 갱신 구독에 대한 iOS 6 스타일 거래 영수증에 대해서만 반환된다.
        # 21007 - 이 영수증은 테스트 환경에서 나온 것이지만, 검증을 위해 프로덕션 환경으로 보냈을 때.
        # 21008 - 이 영수증은 프로덕션 환경에서 생성되었지만, 검증을 위해 테스트 환경으로 보냈을 때.
        # 21009 - 내부 데이터 액세스 오류. 나중에 다시 시도.
        # 21010 - 시스템에서 사용자 계정을 찾을 수 없거나 사용자 계정이 삭제되었을 때.
        # 출처: https://developer.apple.com/documentation/appstorereceipts/status

        is_valid = False
        is_test = False

        if response_status == 21007:
            print("Sandbox receipt detected, redirecting to sandbox URL")
            req = Request(
                SANDBOX_URL, request_data, {"Content-Type": "application/json"}
            )
            response = json.loads(urlopen(req).read().decode("utf-8"))
            response_status = response.get("status")
            print(f"iOS 테스트 영수증 검증 결과 상태코드: {response_status}")
            is_test = True

        if response_status == 0:
            is_valid = True
        else:
            is_valid = False

        # 영수증 정보 확인
        receipt_info = response.get("receipt", {})
        print(f"iOS receipt 정보: {receipt_info}")

        # 테스트 영수증인지 2차 확인 - 1000000 또는 2000000으로 시작하는 구매 ID
        if not is_test:
            in_app_purchases = receipt_info.get("in_app", [])
            print(f"in_app_purchases: {in_app_purchases}")
            if in_app_purchases:
                for purchase in in_app_purchases:
                    print(f"purchase: {purchase}")
                    transaction_id = purchase.get("transaction_id", "")
                    if transaction_id.startswith(
                        "1000000"
                    ) or transaction_id.startswith("2000000"):
                        is_test = True
                        print(
                            f"Test purchase detected by transaction ID: {transaction_id}"
                        )
                        break

        return {
            "is_valid": is_valid,
            "purchase_data": receipt_info,
            "is_test": is_test,
        }
    except Exception as e:
        error_message = str(e)
        print(f"iOS verification error: {error_message}")
        return {
            "is_valid": False,
            "error": f"Verification error: {error_message}",
        }


def save_purchase_history_idolmaster(email, platform, product_id, receipt, status):
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
        "receipt": receipt if isinstance(receipt, str) else str(receipt),
        "platform": platform,
        "product_id": product_id,
        "status": status,
    }
    purchase_table.put_item(Item=item)


def charge_product(email, platform, product_id):
    """Dart/Gem 충전"""
    # 충전 Key 생성
    key = str(uuid.uuid4())
    api_alias = os.environ["API_ALIAS"]
    timestamp_at = round(Decimal(datetime.now().timestamp()), 3)
    table = (
        "idolmaster_key_temporary"
        if api_alias == const.ALIAS_PROD
        else f"{api_alias}_idolmaster_key_temporary"
    )
    db_table = boto3.resource("dynamodb").Table(table)
    db_table.put_item(Item={
        "uuid": key,
        "created_at": timestamp_at,
        "used": False
    })

    # 충전 API 호출
    lambda_name = "idolmaster-api"
    path = f"/public/products/{product_id}/charges"
    body = {"email": email, "platform": platform, "key": key}
    return invoke.invoke_lambda_rest_api(lambda_name, "POST", path, body)


def get_android_publisher_key():
    """안드로이드 구매 영수증 검증을 위한 키 조회"""
    PARAMETER_NAME = "/KEY_FILE/android_publisher_key"
    ssm = boto3.client("ssm")
    res = ssm.get_parameter(
        Name=PARAMETER_NAME,
        WithDecryption=True
    )
    return res["Parameter"]["Value"]
