import os

import boto3

import const


s3_client = boto3.client("s3")


def get_object(bucket_name: str, key: str) -> bytes:
    """S3 버킷 파일 조회

    :param bucket_name: 버킷 이름
    :param key: 버킷 내에서 조회 할 경로

    :return: 파일 내용
    """
    print(f"get_object bucket_name: {bucket_name}, key: {key}")
    return (
        s3_client.get_object(Bucket=bucket_name, Key=key)["Body"].read()
    )


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
