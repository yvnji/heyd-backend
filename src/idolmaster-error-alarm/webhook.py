import json
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError


HOOK_URL = (
    "https://hooks.slack.com/services/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"
)


def to_slack(msg):
    slack_msg = {"text": msg}
    req = Request(HOOK_URL, json.dumps(slack_msg).encode("utf-8"))
    try:
        response = urlopen(req)
        res = response.read()
        print("Message posted :", res)
    except HTTPError as e:
        print("Request failed: %d %s", e.code, e.reason)
    except URLError as e:
        print("Server connection failed: %s", e.reason)
