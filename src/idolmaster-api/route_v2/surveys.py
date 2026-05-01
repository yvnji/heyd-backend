from service import product as product_module


def get_surveys(event, context, params):
    """설문조사 링크 조회
    post_get_survey_link 수정
    return link -> links 수정
    """
    email = event["requestContext"]["authorizer"]["email"]
    return {"data": {"links": [product_module.get_survey_link(email)]}}
