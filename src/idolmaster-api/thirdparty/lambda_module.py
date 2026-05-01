import json
import os

from lib.client import lambda_client


def invoke(
    lambda_function: str,
    payload: dict,
    use_alias: bool = False,
    invoke_type: str = "RequestResponse"
) -> dict:
    """Lambda 호출

    :param lambda_function: 호출 할 람다 이름
    :param payload: 호출 파라미터
    :use_alias: 별칭 사용 여부
    :invoke_type: 람다 호출 타입
        'RequestResponse': 동기 호출
            - return response.Payload
            - response.StatusCode = 200
        'Event': 비동기 호출
            - no return response.Payload
            - response.StatusCode = 202
        'DryRun': 실제 호출하지 않고 해당 람다를 호출할 권한이 있는지만 확인
            - no return response.Payload
            - response.StatusCode = 204

    :return: response of lambda_client.invoke() (boto3 공식 문서 참고)
        {
            'StatusCode': int,
            'FunctionError': str,
            'LogResult': str,
            'Payload': StreamingBody(),
            'ExecutedVersion': str
        }
    """
    lambda_name = lambda_function
    if use_alias:
        api_alias = os.environ["API_ALIAS"]
        lambda_name = f"{lambda_name}:{api_alias}"
    ret = lambda_client.invoke(
        FunctionName=lambda_name,
        InvocationType=invoke_type,
        Payload=json.dumps(payload),
    )
    print(f"[Invoke] Lambda : {lambda_name}, response : {ret}")
    if ret.get("Payload"):
        payload_data = ret["Payload"].read()
        print(f"payload_data : {payload_data}")
        try:
            ret["Payload"] = json.loads(payload_data)
        except json.JSONDecodeError as e:
            print(f"JSONDecodeError : {e}")
            ret["Payload"] = payload_data
    return ret
