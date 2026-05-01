import os
import traceback

import const
from lib.exception import IdolmasterException
from service import avatar
from service import notification
from thirdparty import s3


def generate_avatar(
    img_path_front: str = None,
    img_path_side: str = None,
    gender: str = None,
    avaturn_user_id: str = None,
    fcm_token: str = None
) -> None:
    """아바턴 아바타 생성

    :param img_path_front: 전면 이미지 경로
    :param img_path_side: 측면 이미지 경로
    :param gender: 성별
    :param avaturn_user_id: 아바턴 사용자 ID
    :param fcm_token: 푸시 알림 토큰
    """
    push_title = "아바타 생성 완료"
    push_body = "아바타 생성 완료"
    push_data = None
    try:
        res = avatar.generate_avatar(
            img_path_front.strip("/"),
            img_path_side.strip("/"),
            gender,
            avaturn_user_id)
        if res[0]:
            push_data = res[1]
        else:
            push_title = "아바타 생성 실패"
            push_body = res[2]
    except IdolmasterException as e:
        push_title = "아바타 생성 실패"
        push_body = e.message
    except Exception as e:
        push_title = "아바타 생성 실패"
        push_body = str(e)
        traceback.print_exc()

    # 푸시 알림 전송
    print(f"push_title : {push_title}")
    print(f"push_body : {push_body}")
    print(f"push_data : {push_data}")
    notification.send_push_notification(
        fcm_token,
        push_title,
        push_body,
        push_data
    )


def preprocess_images(image_file_path: str = None, gender: str = None, fcm_token: str = None) -> None:
    """이미지 전처리
    전처리 후 S3 업로드 된 이미지 파일 경로를 클라이언트에게 알림 푸시

    :param image_file_path: 이미지 파일 경로
    :param gender: 성별 (male or female)
    :param fcm_token: 푸시 알림 토큰
    """
    s3_key_prefix = "_".join(image_file_path.split("_")[:-1])
    push_title = "이미지 전처리 완료"
    push_body = "이미지 전처리 완료"
    push_data = None

    # 전처리 할 원본 이미지 다운로드
    oritin_img_data = s3.get_object(
        const.S3_BUCKET_NAME[os.environ["AWS_REGION"]][os.environ["API_ALIAS"]],
        image_file_path)

    # 이미지 전처리
    try:
        img_data = avatar.preprocess_images(oritin_img_data, gender, s3_key_prefix)
        push_data = {
            "image_path_trans_front": "/" + img_data["image_path_front"],
            "image_path_trans_side": "/" + img_data["image_path_side"]
        }
    except IdolmasterException as e:
        push_title = "이미지 전처리 실패"
        push_body = e.message
    except Exception as e:
        push_title = "이미지 전처리 실패"
        push_body = str(e)
        traceback.print_exc()

    # 푸시 알림 전송
    print(f"push_title : {push_title}")
    print(f"push_body : {push_body}")
    print(f"push_data : {push_data}")
    notification.send_push_notification(
        fcm_token,
        push_title,
        push_body,
        push_data
    )
