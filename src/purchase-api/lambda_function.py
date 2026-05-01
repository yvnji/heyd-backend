import json
import os
import traceback
from lib.parser import camel_to_snake
from lib.response import response_lambda
from lib.exception import IdolmasterException

import sentry_sdk
from sentry_sdk.integrations.aws_lambda import AwsLambdaIntegration

SENTRY_DSN = os.environ.get("SENTRY_DSN")
sentry_sdk.init(dsn=SENTRY_DSN, integrations=[AwsLambdaIntegration()])


def routing_method(module: str, function_name: str):
    m = __import__(f"route.{module}", fromlist=[function_name])
    return getattr(m, function_name)


def lambda_handler(event, context):
    # test 주석입니다
    try:
        print(json.dumps(event))
    except Exception:
        print(event)

    stage = event["requestContext"]["stage"]  # stage : prod / staging / dev
    os.environ["API_ALIAS"] = stage
    http_method = event["httpMethod"].lower()
    proxy_path = event["path"].strip("/").split("/")
    module, method = proxy_path
    body = json.loads(event["body"])
    if http_method in ("get", "delete"):
        params = event["queryStringParameters"]
        params = params if params else {}
    else:
        params = body

    try:
        print(f" ==========  [{stage}] {method} Start : {body['email']} ========== ")
        return_code = 1
        function_name = "_".join([http_method, camel_to_snake(method)]).replace(
            "-", "_"
        )
        ret = routing_method(module, function_name)(event, context, params)
        print(f" ==========  [{stage}] {method} End : {ret} ========== ")
        return response_lambda(return_code, {"data": ret} if ret else {})

    except IdolmasterException as e:
        print(f" ====== !! [{stage}] ERROR: {traceback.format_exc()} ======")
        return response_lambda(e.result_code)

    except Exception as e:
        sentry_sdk.capture_exception(e)
        print(f" ====== !! [{stage}] ERROR: {traceback.format_exc()} ======")
        return_code = 0
        return response_lambda(return_code)
