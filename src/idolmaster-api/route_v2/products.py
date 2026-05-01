import const
from lib.decorator import mandatory_params
from lib.exception import IdolmasterResourceNotFoundExeption
from service import product as product_module


def get_products(event, context, params):
    """사용자의 현재 다트, 젬 조회
    post_get_product 수정
    """
    email = event["requestContext"]["authorizer"]["email"]
    return {"data": product_module.get_product(email)}


@mandatory_params(["products", "platform"])
def post_products_accesses(event, context, body):
    """사용자가 결제에 접근 시점 등록
    post_access_product 수정
    """
    email = event["requestContext"]["authorizer"]["email"]
    product_id = body["products"]
    platform = body["platform"]

    # platform 확인
    if platform not in (const.PLATFORM_GOOGLE_PLAY, const.PLATFORM_APP_STORE, const.PLATFORM_PORTONE):
        raise IdolmasterResourceNotFoundExeption(message="platform not found")

    # 상품 이름 확인
    products = product_module.dict_products(platform)
    print(products)
    if product_id not in products:
        raise IdolmasterResourceNotFoundExeption(
            message="product_id not found",
            result_code=1)

    product_module.access_product(email, platform, products[product_id]["charge_type"])


#######################################################
# path 시작이 /products/ 아닌 API
#######################################################


def get_products_charges(event, context, params):
    """요금에 따른 제품 충전 종류 조회
    post_list_charge_type 수정
    """
    return {"data": product_module.list_charge_type()}
