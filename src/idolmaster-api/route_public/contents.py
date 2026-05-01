import const
from lib.exception import IdolmasterBadRequestException
from service import content as content_module


def get_contents(event, context, params):
    """컨텐츠 조회"""
    content_id = params.get("contents")
    ret = None

    # check params
    try:
        content_type = params.get("type", const.CONTENT_TYPE_CHATROOM)
        assert content_type in (const.CONTENT_TYPE_CHATROOM)
    except AssertionError:
        raise IdolmasterBadRequestException(message="Invalid params", result_code=1)

    # 단일 상세 조회
    if content_id:
        ret = {}
        if content_type == const.CONTENT_TYPE_CHATROOM:
            ret = content_module.get_content_chatroom_detail(content_id)
            if ret:
                del ret["chatroom_activated"]

    # 리스트 조회
    else:
        ret = []
        if content_type == const.CONTENT_TYPE_CHATROOM:
            search = params.get("search")
            category = params.get("category")
            main = category == const.CONTENT_CATEGORY_MAIN

            # check params
            try:
                # 정렬 기준
                # 1: 컨텐츠 생성 시간 내림차순
                # 2: 좋아요 수 내림차순
                # 3: 사용자 수 내림차순
                order_type = int(params.get("order_type", 1))

                page = int(params.get("page", 1))
                page_size = int(params.get("page_size", 20))
                offset = (page - 1) * page_size
                assert 1 <= page and 1 <= page_size
                assert order_type in [1, 2, 3]
            except (ValueError, AssertionError):
                raise IdolmasterBadRequestException(message="Invalid params", result_code=1)

            ret = content_module.list_content_chatroom(
                const.CONTENT_RATING_GENERAL,
                order_type,
                search=search,
                category=category if not main else None,
                main=main,
                page_size=page_size,
                offset=offset
            )

    return {"data": ret}


#######################################################
# path 시작이 /contents/ 아닌 API
#######################################################


def get_contents_categories(event, context, params):
    """컨텐츠 카테고리 순서 조회"""
    res = content_module.list_category()
    return {"data": [r["category"] for r in res]}


def get_contents_tags(event, context, params):
    """컨텐츠 태그 조회"""
    res = content_module.list_tag()
    return {"data": [r["tag"] for r in res]}
