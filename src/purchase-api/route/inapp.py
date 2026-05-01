import json
import os

from lib import webhook
from service import inapp
import const


def post_verify_receipt_idolmaster(event, context, params):
    """Hey.D 결제 영수증 검수"""
    email = params["email"]
    product_id = params["id"]
    platform = params["platform"]
    receipt = json.loads(params["encrypted_receipt"])
    ret = {"is_valid": False}
    purchase_status = ""
    verification_result = None

    # encrypted_receipt = params["encrypted_receipt"]
    # If already a dict, use directly
    # if isinstance(encrypted_receipt, dict):
    #     receipt = encrypted_receipt
    # else:
    #     # If it's a string, try to parse it
    #     try:
    #         # Try standard JSON parsing first
    #         receipt = json.loads(encrypted_receipt)
    #     except json.JSONDecodeError:
    #         try:
    #             # If JSON parsing fails, try ast.literal_eval for Python dict format
    #             import ast

    #             receipt = ast.literal_eval(encrypted_receipt)
    #         except (SyntaxError, ValueError) as e:
    #             print(f"Receipt parsing error: {e}")
    #             return {"is_valid": False, "error": "Invalid receipt format"}

    # 클라이언트 상태가 purchased일 때만 영수증 검증 진행
    if receipt.get("status") == "purchased":
        # 영수증 검증
        verification_result = inapp.verify_receipt(platform, receipt)

        is_test = verification_result.get("is_test", False)
        is_valid = verification_result.get("is_valid", False)
        if is_test:
            # 테스트 모드
            print(f"It's test purchase (is_test : {is_test})")
            print(f"Test purchase receipt validation result : {is_valid}")
            purchase_status = const.PURCHASE_STATUS_TEST
            ret["is_valid"] = True

            res_charge = inapp.charge_product(email, platform, product_id)[
                "Payload"
            ]
            print(f"User purchase charged: {res_charge}")

            # 슬랙 알림
            webhook.heyd_to_slack(
                email, product_id, platform, os.environ["API_ALIAS"], test_mode=True
            )

        else:
            print(f"It's actual purchase (is_test : {is_test})")
            print(f"Actual purchase receipt validation result : {is_valid}")
            # 실제로 결제된 경우
            if is_valid:
                ret["is_valid"] = True

                res_charge = inapp.charge_product(email, platform, product_id)[
                    "Payload"
                ]
                print(f"User purchase charged: {res_charge}")

                # 실제 결제
                purchase_status = const.PURCHASE_STATUS_SUCCESS

                # 슬랙 알림
                webhook.heyd_to_slack(
                    email, product_id, platform, os.environ["API_ALIAS"]
                )
            else:
                # 결제 검증 실패
                purchase_status = const.PURCHASE_STATUS_FAILED
    elif receipt.get("status") == "canceled":
        purchase_status = const.PURCHASE_STATUS_FAILED
    else:
        purchase_status = const.PURCHASE_STATUS_UNKNOWN

    # 이력 저장
    inapp.save_purchase_history_idolmaster(
        email, platform, product_id, receipt, purchase_status
    )

    print(f"verification : {verification_result}")
    print(f"Final verification result: {ret}")
    return ret
