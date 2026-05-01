import json
import os

import routing_api


def lambda_handler(event, context):
    # test 주석입니다
    try:
        print(json.dumps(event))
    except Exception:
        print(event)

    stage = event["requestContext"]["stage"]  # stage : prod / staging / dev

    # for test
    if stage == "test":
        stage = "dev"  # 기존 cognito pool을 staging에서 사용 중

    os.environ["API_ALIAS"] = stage

    # Websocket API
    if event.get("requestContext", {}).get("routeKey"):
        return routing_api.websocket_api(event, context)

    # REST API
    else:
        return routing_api.rest_api(event, context)
