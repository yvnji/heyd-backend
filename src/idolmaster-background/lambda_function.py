import json
import os
import traceback
from typing import Callable

from route import avatars


MODULES = {
    "avatars": avatars
}


def routing_method(module: str, function_name: str) -> Callable:
    """함수 라우팅

    :param module: 모듈 이름
    :param function_name: 함수 이름

    :return: 라우팅된 함수
    """
    try:
        if module not in MODULES:
            raise ModuleNotFoundError

        m = MODULES[module]
        if function_name not in dir(m):
            raise ModuleNotFoundError

        return getattr(m, function_name)
    except ModuleNotFoundError:
        raise Exception("Invalid function name")


def lambda_handler(event, context):
    try:
        print(json.dumps(event))
    except Exception:
        print(event)

    api_alias = event["api_alias"]
    module = event["module"]
    function_name = event["function_name"]
    body = event.get("body", {})
    print(f" ========== [{api_alias}] {module}.{function_name} Start (event : {event}) ========== ")
    os.environ["API_ALIAS"] = api_alias

    try:
        func = routing_method(module, function_name)
        res = func(**body)
        print(f" ====== [{api_alias}] {module}.{function_name} : {res} ======")
        return res

    except Exception:
        print(f" ====== !! [{api_alias}] ERROR: {traceback.format_exc()} ======")
