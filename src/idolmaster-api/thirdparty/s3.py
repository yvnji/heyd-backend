import os

from botocore.exceptions import ClientError

import const
from lib.client import s3_client
from lib.exception import IdolmasterResourceNotFoundExeption


def check_object(bucket_name: str, key: str) -> None:
    """S3 버킷에 key에 해당하는 object가 존재하는지 확인.
    존재하지 않을 경우 403 에러 발생

    :param bucket_name: 버킷 이름
    :param key: 버킷 내에서 조회 할 경로
    """
    try:
        s3_client.get_object(Bucket=bucket_name, Key=key)
    except ClientError as e:
        if e.response["Error"]["Code"] == "NoSuchKey":
            raise IdolmasterResourceNotFoundExeption
        else:
            raise Exception(f"{e}")


def get_object(bucket_name: str, key: str) -> str:
    """S3 버킷 파일 조회

    :param bucket_name: 버킷 이름
    :param key: 버킷 내에서 조회 할 경로

    :return: 파일 내용
    """
    print(key)
    return (
        s3_client.get_object(Bucket=bucket_name, Key=key)["Body"].read().decode("utf-8")
    )


def get_s3_file_path_temp(filepath, expiresec, removeURL):
    """S3 임시 url 생성"""
    # file_path = preset_character/ElonMusk_idle.glb
    # result = s3.generate_presigned_url(
    #     "get_object",
    #     Params={"Bucket": "idolmaster-asset", "Key": filepath},
    #     ExpiresIn=expiresec,
    # )
    # if removeURL:
    #     result = result.replace(s3_bucket_url, "")

    result = f"https://asset.hey-d.ai/{filepath}"
    if os.environ["API_ALIAS"] in [const.ALIAS_DEV, const.ALIAS_STAGE]:
        result = f"/{filepath}"
    return result


def list_files(bucket_name: str, prefix: str) -> list:
    """S3 버킷 폴더 내의 파일 리스트 조회

    :param bucket_name: 버킷 이름
    :param prefix: 버킷 내에서 조회 할 경로

    :return: directory 안의 파일 이름 리스트
    """
    prefix = prefix.strip("/") + "/" if prefix else ""
    objects_list = []
    res = s3_client.list_objects_v2(Bucket=bucket_name, Prefix=prefix)

    if res.get("Contents"):
        objects_list = [
            content["Key"] for content in res["Contents"] if content["Key"] != prefix
        ]

    return sorted(objects_list)


def upload_file(key: str, data: bytes) -> None:
    """S3 버킷에 파일 업로드

    :param key: 버킷 내 저장 할 경로
    :param data: 저장 할 파일 데이터
    """
    bucket_name = const.S3_BUCKET_NAME[os.environ["AWS_REGION"]][
        os.environ["API_ALIAS"]
    ]
    print(f"PUT s3_bucket_name: {bucket_name}, key: {key}")
    s3_client.put_object(
        Bucket=bucket_name,
        Key=key,
        Body=data,
    )
