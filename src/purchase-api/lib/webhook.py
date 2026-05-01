import datetime
import json
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

import const


def heyd_to_slack(user_id: str, product_id: str, platform: str, stage: str, test_mode: bool = False) -> None:
    """heyd 결제 발생할 경우 웹훅 생성

    :param user_id: 사용자 id (email)
    :param product_id: 등록된 제품 Id (e.g. dart_099)
    :param platform: 구매한 플랫폼
    :param stage: 배포 서버
    :param test_mode: 테스트 모드 여부
    """
    if (
        stage == const.ALIAS_PROD
        and not test_mode
    ):
        HOOK_URL = "https://hooks.slack.com/services/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"
    else:
        HOOK_URL = "https://hooks.slack.com/services/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"
        if test_mode:
            platform = platform + " (TEST)"

    slack_msg = {
        "text": "In-App Purchase Event",
        "attachments": [
            {
                "fields": [
                    {"title": "User ID", "value": user_id, "short": True},
                    {"title": "Product ID", "value": product_id, "short": True},
                    {
                        "title": "Amount",
                        "value": f"${const.PRODUCT_PRICE[product_id]}",
                        "short": True,
                    },
                    {"title": "Platform", "value": platform, "short": True},
                    {"title": "Stage", "value": stage, "short": True},
                ],
                "footer": "In-App Purchase Notification",
                "ts": int(datetime.datetime.now().timestamp()),
            }
        ],
    }
    req = Request(HOOK_URL, json.dumps(slack_msg).encode("utf-8"))
    try:
        response = urlopen(req)
        res = response.read()
        print("Message posted :", res)
    except HTTPError as e:
        print("[ERROR] Request failed: %d %s", e.code, e.reason)
    except URLError as e:
        print("[ERROR] Server connection failed: %s", e.reason)
