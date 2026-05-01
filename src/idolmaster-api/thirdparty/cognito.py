import json
import os

import const
from lib.client import cognito_client as client


def get_user_by_email(email: str) -> dict:
    """Cognito 유저 정보를 email을 통해 조회

    :param email: Cognito email

    :return:
        {
            'sub': str,
            'username': str,
            'email': str,
            'email_verified': bool,  (email 검증 유무)
            'provider_name': str || None,  (외부 공급자  e.g. Google, SignInWithApple, Facebook)
            'enabled': bool  (계정 활성화 유무)
        }
    """
    user_item = {}
    res = client.list_users(
        UserPoolId=const.COGNITO_USER_POOL_ID[os.environ["AWS_REGION"]][
            os.environ["API_ALIAS"]
        ],
        Filter=f'email = "{email}"',
    )["Users"]
    if res and len(res) == 1:
        user_item = {
            "username": res[0]["Username"],
            "provider_name": None,
            "enabled": res[0]["Enabled"],
        }
        for attr in res[0]["Attributes"]:
            if attr["Name"] == "email":
                user_item["email"] = attr["Value"]
            elif attr["Name"] == "sub":
                user_item["sub"] = attr["Value"]
            elif attr["Name"] == "email_verified":
                user_item["email_verified"] = json.loads(attr["Value"])
            elif attr["Name"] == "identities":
                user_item["provider_name"] = json.loads(attr["Value"])[0][
                    "providerName"
                ]
    return user_item


def get_login_platform_by_email(email: str) -> str:
    """
    이메일로 사용자 로그인 플랫폼 확인
    """
    response = client.list_users(
        UserPoolId=const.COGNITO_USER_POOL_ID[os.environ["AWS_REGION"]][
            os.environ["API_ALIAS"]
        ],
        Filter=f'email = "{email}"',
        Limit=1,
    )

    users = response.get("Users", [])
    if not users:
        return "unknown"

    user = users[0]

    # 사용자 정보에서 ID 제공자 확인
    identities = None
    for attr in user.get("Attributes", []):
        if attr["Name"] == "identities":
            identities = json.loads(attr["Value"])
            break

    # ID 제공자가 없으면 일반 이메일 회원가입으로 간주
    if not identities:
        return "email"

    # ID 제공자 정보에서 플랫폼 확인
    provider_name = identities[0].get("providerName", "").lower()

    if provider_name == "google":
        return "google"
    elif provider_name == "signinwithapple":
        return "apple"
    elif provider_name == "facebook":
        return "facebook"
    else:
        return provider_name if provider_name else "unknown"
