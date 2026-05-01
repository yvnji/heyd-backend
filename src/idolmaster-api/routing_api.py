import json
import os
import traceback
from typing import Callable, Any

import const
from lib.exception import IdolmasterException, IdolmasterResourceNotFoundExeption
from lib.parser import camel_to_snake, decimal_encoder, encode_multipart_form_data

import sentry_sdk
from sentry_sdk.integrations.aws_lambda import AwsLambdaIntegration

SENTRY_DSN = os.environ.get("SENTRY_DSN")
sentry_sdk.init(dsn=SENTRY_DSN, integrations=[AwsLambdaIntegration()])


def http_response(
    version: str,
    status_code: int,
    result_code: int,
    body: dict = {},
    headers: dict = {},
) -> dict:
    headers_cors = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "DELETE,GET,HEAD,OPTIONS,PATCH,POST,PUT",
        "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
        "Document-Policy": "js-profiling",  # Sentry 브라우저 프로파일링을 위한 옵션
    }
    ret = {"statusCode": status_code, "headers": {**headers_cors, **headers}}

    if version == const.API_VERSION_V1:
        if body.get("result") is None:
            body["result"] = result_code

    # response.result : Code of Exception each statusCode
    else:
        if result_code is not None:
            body["code"] = result_code

    try:
        ret["body"] = json.dumps(body, default=decimal_encoder)
    except Exception as e:
        print("body encoding error :", e)
        print(f"body : {body}")
        ret["body"] = json.dumps(body, default=str)

    return ret


def parse_path(http_method: str, proxy_path: str) -> tuple:
    """path parameter를 코드 내에서 사용될 함수 이름과 파라미터로 변환.

    :param http_method: HTTP Method
    :param proxy_path: URI path

    :return
        (
            str,  (API version)
            str,  (라우팅될 모듈 이름)
            str,  (라우팅될 메서드 이름)
            dict  (path parameter에 들어있는 변수)
                {
                    '{key}': '{value}'
                }
        )
    """
    path_split = proxy_path.replace("-", "_").strip("/").split("/")   # path format : /{version}/{endpoint}

    try:
        assert 1 < len(path_split)

        version = path_split[0]
        # module = camel_to_snake(path_split[1]).replace("-", "_").split("_")[0]
        module = camel_to_snake(path_split[1])
        method = None
        path_params = {}

        # 아바턴 Webhook에서 사용 (path : /render/ready)
        if version == "render" and path_split[1] == "ready":
            version = const.API_VERSION_PUBLIC
            module = "render"
            path_split = [version, "render-ready"]

        # path format : /api/{module}/{method}
        if version == const.API_VERSION_V1:
            method = "_".join([http_method, camel_to_snake(path_split[2])]).replace(
                "-", "_"
            )

        # path format : /v2 or public/{URI_path_parameters}
        elif version in [const.API_VERSION_V2, const.API_VERSION_PUBLIC]:
            method = http_method
            path_params_list = path_split[1:]
            params_count = len(path_params_list) // 2 * 2
            for i in range(0, params_count, 2):
                path_params[path_params_list[i]] = path_params_list[i + 1]
                method += "_" + camel_to_snake(path_params_list[i])
            if len(path_params_list) % 2 == 1:
                method += "_" + camel_to_snake(path_params_list[-1])
            method = method.replace("-", "_")

        else:
            assert False

    except AssertionError:
        raise IdolmasterResourceNotFoundExeption(message="Invalid path", result_code=-1)

    print(version, module, method, path_params)
    return version, module, method, path_params


def routing_method(
    version: str, module: str, function_name: str
) -> Callable[[dict, dict, dict], Any]:
    """API에 맞는 함수로 라우팅

    :param version: API version (public, api or v2)
    :param module: API 모듈 이름
    :param function_name: API 연결된 함수 이름

    :return: 라우팅된 함수
    """
    print(version, module, function_name)
    if version == const.API_VERSION_V1:
        route_dir = "route"
    elif version == const.API_VERSION_V2:
        route_dir = "route_v2"
    elif version == const.API_VERSION_PUBLIC:
        route_dir = "route_public"
    else:
        raise IdolmasterResourceNotFoundExeption(message="Invalid path", result_code=-1)

    try:
        m = __import__(f"{route_dir}.{module}", fromlist=[function_name])
        if function_name not in dir(m):
            raise ModuleNotFoundError
    except ModuleNotFoundError:
        module_split = module.split("_")
        if len(module_split) > 1:
            print(f"change module : {module} -> {module_split[0]}")
            return routing_method(version, module_split[0], function_name)
        else:
            raise IdolmasterResourceNotFoundExeption(message="Invalid path", result_code=-1)
    return getattr(m, function_name)


def rest_api(event, context):
    version = None
    try:
        api_alias = os.environ["API_ALIAS"]
        http_method = event["httpMethod"].lower()
        content_type = event["headers"].get(
            "content-type", event["headers"].get("Content-Type", "")
        )
        version, module, method, path_params = parse_path(http_method, event["path"])

        try:
            if "multipart/form-data" in content_type:
                body = encode_multipart_form_data(event["body"], content_type)
            else:
                body = json.loads(event["body"])
        except Exception as e:
            print("invalid json body :", e)
            body = event["body"]

        if http_method in ("get", "delete"):
            params = event["queryStringParameters"]
            params = params if params else {}
        else:
            params = body if body else {}
        params.update(path_params)
        print("params :", params)

        print(
            f" ==========  [{api_alias}] {method} Start (event : {event}) ========== "
        )
        return_code = 1 if version == const.API_VERSION_V1 else None
        headers = {}
        ret = routing_method(version, module, method)(event, context, params)

        if (isinstance(ret, list) or isinstance(ret, tuple)) and len(ret) == 2:
            headers, ret = ret
        res = http_response(version, 200, return_code, ret if ret else {}, headers)
        print(f" ==========  [{api_alias}] {method} End (response : {res}) ========== ")
        return res

    except IdolmasterException as e:
        sentry_sdk.capture_exception(e)
        print(f" ====== !! [{api_alias}] WARNING: {e.message} ======")
        return http_response(
            version, e.status_code, e.result_code, {"message": e.message}, e.headers
        )

    except Exception as e:
        sentry_sdk.capture_exception(e)
        print(f" ====== !! [{api_alias}] ERROR: {traceback.format_exc()} ======")
        return http_response(version, 500, 0, {"message": "Internal Server Error"})


def websocket_api(event, context):
    try:
        api_alias = os.environ["API_ALIAS"]
        body = json.loads(event.get("body", "{}"))
        method = camel_to_snake(event["requestContext"]["routeKey"])
        module = "websocket"
        version = const.API_VERSION_V1

        print(
            f" ==========  [{api_alias}] {method} Start (event : {event}) ========== "
        )
        res = routing_method(version, module, method)(event, context, body)
        print(f" ==========  [{api_alias}] {method} End (response : {res}) ========== ")
        return res
    except IdolmasterException as e:
        sentry_sdk.capture_exception(e)
        print(f" ====== !! [{api_alias}] {e.message}: {traceback.format_exc()} ======")
        return {}
    except Exception as e:
        sentry_sdk.capture_exception(e)
        print(f" ====== !! [{api_alias}] ERROR: {traceback.format_exc()} ======")
        return {}
