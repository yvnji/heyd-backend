import boto3
import json
import os


def invoke_lambda_http_api(lambda_function: str, api: str, payload: dict):
    """API Gateway HTTP API 연결된 Lambda를 직접 호출"""
    api_alias = os.environ["API_ALIAS"]
    lambda_client = boto3.client("lambda")
    ret = lambda_client.invoke(
        FunctionName=f"{lambda_function}:{api_alias}",
        InvocationType="RequestResponse",
        Payload=json.dumps(
            {
                "requestContext": {"stage": api_alias, "http": {"method": api_alias}},
                "pathParameters": {"action": api},
                "body": json.dumps(payload),
            }
        ),
    )
    if ret.get("Payload"):
        ret["Payload"] = json.loads(ret["Payload"].read())
    return ret


def invoke_lambda_rest_api(
    lambda_function: str, http_method: str, path: str, data: dict, payload: dict = None
):
    """API Gateway REST API 연결된 Lambda 직접 호출"""
    api_alias = os.environ["API_ALIAS"]
    lambda_client = boto3.client("lambda")
    body = None
    params = None
    if http_method.upper() in ["POST", "PUT"]:
        body = json.dumps(data)
    elif data:
        params = data
    payload_upload = {
        "requestContext": {"stage": api_alias},
        "httpMethod": http_method.upper(),
        "path": path,
        "body": body,
        "queryStringParameters": params,
        "headers": {},
    }
    if payload:
        payload_upload.update(payload)

    ret = lambda_client.invoke(
        FunctionName=f"{lambda_function}:{api_alias}",
        InvocationType="RequestResponse",
        Payload=json.dumps(payload_upload),
    )
    if ret.get("Payload"):
        ret["Payload"] = json.loads(ret["Payload"].read())
    return ret
