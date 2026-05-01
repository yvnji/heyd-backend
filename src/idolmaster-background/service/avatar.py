import base64
import json
import os
import urllib3
from urllib3 import encode_multipart_formdata

import const
from lib import time
from lib.decorator import func_timeout
from lib.http_request import request
from thirdparty import avaturn
from thirdparty import s3


@func_timeout(const.AVATURN_GENERATE_AVATAR_TIMEOUT)
def generate_avatar(
    img_path_front: str = None,
    img_path_side: str = None,
    gender: str = None,
    avaturn_user_id: str = None
) -> tuple[bool, dict, str]:
    """아바턴 아바타 생성

    :param img_path_front: 전면 이미지 경로
    :param img_path_side: 측면 이미지 경로
    :param gender: 성별
    :param avaturn_user_id: 아바턴 사용자 ID

    :return: 아바타 생성 결과
        (
            bool,   # 성공 여부
            {
                "id": str,     # url to apply assets to avatar
                "url": str     # session id (avatar ID)
            },
            str   # 에러 메시지
        )
    """
    ch_ret = False
    data = {}
    err_msg = ""

    # 아바타 생성 시작
    response = avaturn.new_avatar(avaturn_user_id)
    print(f"create_new_avatar response : {response}")

    # 이미지 업로드
    if response["status_code"] == 200:
        upload_data = response["response"]
        avatar_id = upload_data["avatar_id"]
        upload_url = upload_data["upload_url"]
        file_binary_f = s3.get_object(const.S3_BUCKET_NAME[os.environ["AWS_REGION"]][os.environ["API_ALIAS"]], img_path_front)
        file_binary_s = s3.get_object(const.S3_BUCKET_NAME[os.environ["AWS_REGION"]][os.environ["API_ALIAS"]], img_path_side)
        fields = {
            "image-frontal": ("image-frontal.jpg", file_binary_f, "image/jpeg"),
            "image-side-1": ("image-side-1.jpg", file_binary_s, "image/jpeg"),
            "image-side-2": ("image-side-2.jpg", file_binary_s, "image/jpeg"),
            "body-type": gender,
            "telephoto": "false",
        }
        encoded_body, content_type = encode_multipart_formdata(fields)
        response = request(
            "POST",
            upload_url,
            headers={"Content-Type": content_type},
            data=encoded_body,
        )
        print(f"upload_image response : {response}")

        # 세션 불러오기
        if response["status_code"] == 200:
            response = avaturn.new_session(avaturn_user_id, avatar_id)
            print(f"create_new_session response : {response}")
            if response["status_code"] == 200:
                data = response["response"]
                data["id"] = avatar_id
                ch_ret = True
            else:
                err_msg = json.dumps(response["response"])
        else:
            err_msg = json.dumps(response["response"])
    else:
        err_msg = json.dumps(response["response"])

    if "custom_upload_url" in data:
        del data["custom_upload_url"]

    return ch_ret, data, err_msg


@func_timeout(const.IMAGE_PREPROCESSING_TIMEOUT)
def preprocess_images(img_data: bytes, gender: str, s3_key_prefix: str) -> dict:
    """이미지 전처리
    전처리 후 이미지 파일 경로를 클라이언트에게 알림 푸시 (S3 업로드)

    :param img_data: 전처리 전 이미지 데이터
    :param gender: 성별
    :param s3_key_prefix: 원본 이미지 파일 경로 접두사 (원본 이미지 경로에서 '_front.jpg' 제외)

    :return: 전처리 후 이미지 파일 경로
        {
            "image_path_front": str,
            "image_path_side": str
        }
    """
    gender_image_generation = 'f'
    target_weight_image_generation = 0.974
    source_weight_image_generation = 1.75
    if gender == 'male':
        gender_image_generation = 'm'
        target_weight_image_generation = 1.174
        source_weight_image_generation = 1.45
    face_swap_params = {
        "performance_selection": "Speed",
        "aspect_ratios_selection": "896*1152",
        "image_prompts": [
            {
                "cn_img": base64.b64encode(img_data).decode('utf-8'),
                "cn_stop": 0.9,
                "cn_weight": target_weight_image_generation,
                "cn_type": "FaceSwap"
            }, {
                "cn_img": gender_image_generation,
                "cn_stop": 0.809,
                "cn_weight": source_weight_image_generation,
                "cn_type": "PyraCanny"
            }
        ],
        "async_process": False,
        "save_extension": "jpg",
        "image_number": 1,
        "image_seed": "1000748121645691857",
        "require_base64": True
    }
    print('img/preprocessing request : ', face_swap_params)
    http = urllib3.PoolManager()
    headers = {"content-type": "application/json; charset=UTF-8"}
    input_data = json.dumps(face_swap_params)
    response = http.request("POST", const.IMAGE_PREPROCESSING_URL, headers=headers, body=input_data)
    response_data = json.loads(response.data.decode('utf-8'))
    print('img/preprocessing response : ', json.dumps(response_data))
    # Base64 헤더 제거
    if "," in response_data[0]['base64']:
        response_data[0]['base64'] = response_data[0]['base64'].split(",")[1]
    file_binary_f = base64.b64decode(response_data[0]['base64'])
    # Base64 헤더 제거
    if "," in response_data[1]['base64']:
        response_data[1]['base64'] = response_data[1]['base64'].split(",")[1]
    file_binary_s = base64.b64decode(response_data[1]['base64'])
    utc_now = time.now()
    utc_now_iso = utc_now.isoformat() + "Z"
    print('img/preprocessing time : ', utc_now_iso)

    # 이미지 S3 업로드
    # image_path_front = f'user_images/{utc_now_iso}_front.jpg'
    # image_trans_front = f'user_images/{utc_now_iso}_trans_front.jpg'
    # image_trans_side = f'user_images/{utc_now_iso}_trans_side.jpg'
    image_trans_front = f'{s3_key_prefix}_trans_front.jpg'
    image_trans_side = f'{s3_key_prefix}_trans_side.jpg'
    # s3.upload_file(image_path_front, img_data)
    s3.upload_file(image_trans_front, file_binary_f)
    s3.upload_file(image_trans_side, file_binary_s)

    return {
        "image_path_front": image_trans_front,
        "image_path_side": image_trans_side
    }
