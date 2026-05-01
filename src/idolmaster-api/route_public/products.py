from lib.decorator import mandatory_params
from lib.exception import IdolmasterBadRequestException
from service import product as product_module


@mandatory_params(["products", "email", "platform", "key"])
def post_products_charges(event, context, body):
    """상품 구매를 통한 다트/젬 충전.
    POST /product/chargeProduct 수정
    현재는 내부 호출용 API(from Lambda 'purchase-api')
    """
    product_id = body["products"]
    email = body["email"]
    platform = body["platform"]
    key = body["key"]

    # check key
    if not product_module.check_key(key):
        raise IdolmasterBadRequestException(message="Invalid key", result_code=1)

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


#######################################################
# path 시작이 /products/ 아닌 API
#######################################################


def get_products_charges(event, context, params):
    """다트 상점 조회"""
    res = product_module.list_charge_type_v2()
    for r in res:
        del r["id"]
    return {"data": res}
