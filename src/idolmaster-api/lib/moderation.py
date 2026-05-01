import os

import const
from lib import client


def moderate_image(s3_path: str = None, img_object: bytes = None) -> bool:
    """
    이미지 검열 함수 - 단순화된 키워드 기반 검열
    S3 경로 or 이미지 데이터로 검열

    Args:
        s3_path: S3에 저장된 이미지 경로
        img_object: byte로 이루어진 이미지 파일

    Returns:
        bool: 부적합 이미지면 True(검열 필요), 적합 이미지면 False(검열 제외)
    """
    # 경로와 데이터 중 하나의 파라미터만 필요
    if (
        all([s3_path, img_object])
        or all([not s3_path, not img_object])
    ):
        raise Exception

    if s3_path:
        bucket = const.S3_BUCKET_NAME[os.environ["AWS_REGION"]][os.environ["API_ALIAS"]]
        response = client.rekognition_client.detect_moderation_labels(
            Image={"S3Object": {"Bucket": bucket, "Name": s3_path}}
        )

    else:
        response = client.rekognition_client.detect_moderation_labels(
            Image={"Bytes": img_object}
        )

    print(f"Detected labels for {s3_path}")

    for label in response["ModerationLabels"]:
        print(
            f"label: {label['Name']}, parents: {label['ParentName']}, level: {label.get('TaxonomyLevel', 'N/A')}"
        )

    needs_moderation = False

    for label in response["ModerationLabels"]:
        label_name = label["Name"]

        # 제외 목록에 없는 레이블이 하나라도 있으면 검열 필요
        if label_name not in const.EXCLUDED_CATEGORIES:
            needs_moderation = True
            print(f"검열 대상 레이블 발견: {label_name}")
        else:
            print(f"검열 제외 레이블: {label_name}")

    print(f"총 감지된 레이블: {len(response['ModerationLabels'])}")
    print(f"검열 결과: {'검열 필요' if needs_moderation else '검열 불필요'}")

    return needs_moderation
