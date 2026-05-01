import os

from lib import webhook
from service import pg


def post_verify_receipt_portone_idolmaster(event, context, params):
    """포트원을 통해 결제한 영수증 검증"""
    email = params["email"]
    imp_uid = params["imp_uid"]
    product_id = params["product_id"]
    amount = params["amount"]
    verification_result = pg.verify_portone_payment(imp_uid, amount)
    if verification_result["is_valid"]:
        pg.save_purchase_history_idolmaster(email, product_id, imp_uid)
        pg.charge_product(email, product_id)
        webhook.heyd_to_slack(email, product_id, "portone", os.environ["API_ALIAS"])
    return verification_result
