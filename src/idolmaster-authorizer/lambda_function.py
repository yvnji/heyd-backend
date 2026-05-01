import json
import os
import re
import sys
import traceback

import boto3
import firebase_admin
import jwt
import requests
from firebase_admin import credentials, auth
from jwt import algorithms

import const
from mariadb import get_db_connection


def generate_policy(effect, resource, context=None):
    """Authorizer Return Type"""
    ret = {
        # "principalId": "asdf",
        "policyDocument": {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Action": "execute-api:Invoke",
                    "Effect": effect,    # Deny : 403
                    "Resource": resource
                }
            ]
        }
    }
    context = validate_context(context)
    if context:
        ret["context"] = context
    print(f"return : {ret}")
    return ret


def get_decoded_token_firebase(id_token):
    """Firebase에 등록된 사용자 정보 확인"""
    decoded_token = None

    try:
        decoded_token = auth.verify_id_token(id_token)
        iss = decoded_token.get("iss", "")
        provider = decoded_token.get("firebase", {}).get("sign_in_provider")

        # Firebase Authentication에서 ID Token 발급
        if "securetoken.google.com" in iss:
            if "apple.com" == provider:
                decoded_token["platform"] = "apple"
            elif "google.com" == provider:
                decoded_token["platform"] = "google"
            elif "facebook.com" == provider:
                decoded_token["platform"] = "facebook"
            else:
                raise Exception(f"IdP Error (provider : {provider})")

        else:
            if "accounts.google.com" in iss:
                decoded_token["platform"] = "google"
            elif "www.facebook.com" in iss:
                decoded_token["platform"] = "facebook"
            elif "appleid.apple.com" in iss:
                decoded_token["platform"] = "apple"
            else:
                raise Exception(f"IdP Error (iss : {iss})")

    except auth.InvalidIdTokenError:
        pass
    except auth.ExpiredIdTokenError:
        raise Exception("Expired Token (Firebase)")

    return decoded_token


def get_decoded_token_cognito(id_token, stage):
    """Cognito에 등록된 사용자 정보 확인"""
    decoded_token = None
    aws_region = os.environ["AWS_REGION"]
    user_pool_id = const.COGNITO_USER_POOL_ID[aws_region][stage]
    client_id = const.COGNITO_CLIENT_ID[aws_region][stage]
    cognito_keys_url = f"https://cognito-idp.{aws_region}.amazonaws.com/{user_pool_id}/.well-known/jwks.json"

    # Cognito public key 조회
    res = requests.get(cognito_keys_url)
    public_keys = res.json()["keys"]
    header = jwt.get_unverified_header(id_token)
    rsa_key = None
    for key in public_keys:
        if key["kid"] == header["kid"]:
            rsa_key = key
            break

    if rsa_key:
        try:
            decoded_token = jwt.decode(
                id_token,
                algorithms.RSAAlgorithm.from_jwk(json.dumps(rsa_key)),
                audience=client_id,    # Token에 aud 있을 경우 (ID token : O, Access token : X)
                issuer=f"https://cognito-idp.{aws_region}.amazonaws.com/{user_pool_id}",
                algorithms=["RS256"]
            )
            decoded_token["platform"] = "cognito"
        except jwt.ExpiredSignatureError:
            raise Exception("Expired Token (Cognito)")
        except jwt.InvalidTokenError:
            pass

    return decoded_token


def get_key_file() -> str:
    """파라미터 스토어에 저장되어 있는 키 파일 조회"""
    PARAMETER_NAME = "/KEY_FILE/firebase_key_file"
    ssm = boto3.client("ssm")
    res = ssm.get_parameter(
        Name=PARAMETER_NAME,
        WithDecryption=True
    )
    return res["Parameter"]["Value"]


def get_user_db(stage: str, email: str) -> dict:
    """MariaDB에 저장된 사용자 정보 조회"""
    user_db = None
    db_connection = get_db_connection(stage)
    with db_connection.cursor() as cursor:
        query = f"""
        select *
        from `user`
        where
            active = 1
            and email = '{email}'
        """
        cursor.execute(query)
        user_db = cursor.fetchone()
    db_connection.close()
    return user_db if user_db else {}


def lambda_handler(event, context):
    try:
        print(json.dumps(event))
        method_arn = event["methodArn"]
        stage_gateway = method_arn.split(":")[-1].split("/")[1]
        authorization_token = event["authorizationToken"]
        if authorization_token[:6] == "Bearer":
            authorization_token = authorization_token.split(" ")[-1]

        # for test
        if stage_gateway == "test":
            stage_gateway = "dev"

        # Firebase Admin SDK 초기화
        try:
            key_file = json.loads(get_key_file())
            cred = credentials.Certificate(key_file)
            firebase_admin.initialize_app(cred)
        except ValueError as e:
            print(e)

        decoded_token = get_decoded_token_firebase(authorization_token)
        if not decoded_token:
            decoded_token = get_decoded_token_cognito(authorization_token, stage_gateway)

        # Token 검증 완료
        if decoded_token:
            print(f"decoded token : {decoded_token}")

            # 사용자 DB 확인
            user_db = get_user_db(
                stage_gateway,
                # decoded_token.get("platform", ""),
                decoded_token.get("email", ""))
            print(f"DB user : {user_db}")

            # DB에 등록되어 있을 경우 인가
            if user_db:
                decoded_token["db_id"] = user_db["id"]
                return generate_policy("Allow", method_arn, context=decoded_token)

            # Status Code : 403
            else:
                return generate_policy("Deny", method_arn, context=decoded_token)
        else:
            print("Invalid Token")

    except Exception:
        traceback.print_exc()

    raise Exception('Unauthorized')    # 401


def validate_context(context):
    """context가 올바른 데이터인지 검사하고 예외 처리"""
    valid_context = {}

    if isinstance(context, dict):
        for key, value in context.items():
            # 키 이름이 올바른지 검사 (알파벳, 숫자, 언더스코어(_)만 허용)
            if not re.match(r'^[a-zA-Z0-9_:]+$', key):
                print(f"잘못된 context 키 이름: '{key}'. 특수 문자 사용 불가")
                continue

            # "AWS"로 시작하는 키 이름 제한
            if key.startswith("AWS"):
                print(f"context 키 '{key}'는 'AWS'로 시작할 수 없습니다.")
                continue

            # 값의 타입 검사 (str, int, float만 허용)
            if not isinstance(value, (str, int, float)):
                if isinstance(value, bool):  # Boolean 값이면 문자열로 변환
                    valid_context[key] = str(value).lower()
                else:
                    print(f"context 값이 지원되지 않는 타입입니다: {key} -> {type(value)}")
                continue

            valid_context[key] = value

        # 전체 context 크기 검사 (10KB 초과 여부)
        context_size = sys.getsizeof(json.dumps(valid_context))
        if context_size >= 10240:
            print(f"context 데이터 크기가 너무 큽니다. ({context_size} bytes)")
            valid_context = {}

    print(f"Valid Context : {valid_context}")
    return valid_context
