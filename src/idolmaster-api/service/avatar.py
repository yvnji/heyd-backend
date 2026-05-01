import base64
import json
import os
import urllib3
from urllib3 import encode_multipart_formdata

import const
from lib import time
from lib.decorator import preprocessing_cursor
from lib.exception import IdolmasterResourceNotFoundExeption
from lib.http_request import request
from thirdparty import avaturn
from thirdparty import s3
from thirdparty import lambda_module


@preprocessing_cursor
def check_file_path(avatar_id: str, cursor: object = None) -> None:
    """아바타 정보에 있는 파일 패스들이 실제 존재하는지 확인.
    파일이 없을 경우 404 에러 발생.

    :param character_id: 캐릭터 id
    :param cursor: pymysql.connect().cursor()
    """
    # 모션, 썸네일 파일 확인
    query = f"""
    SELECT
        avatar_file_path,
        thumbnail_file_path
    FROM
        `avatar`
    WHERE
        avatar_id = '{avatar_id}'
    """
    cursor.execute(query)
    item = cursor.fetchone()
    try:
        s3.check_object(
            const.S3_BUCKET_NAME[os.environ["AWS_REGION"]][os.environ["API_ALIAS"]],
            item["avatar_file_path"]
        )
        # s3.check_object(
        #     const.S3_BUCKET_NAME[os.environ["AWS_REGION"]][os.environ["API_ALIAS"]],
        #     item["thumbnail_file_path"]
        # )
    except IdolmasterResourceNotFoundExeption:
        raise IdolmasterResourceNotFoundExeption(f"File path not found (avatar id : {avatar_id})")


def create_export(avatar_id: str):
    data = {}
    res = avaturn.create_export(avatar_id)
    if res["status_code"] == 200:
        data = res["response"]

    return data


def create_user():
    data = {}
    res = avaturn.create_user()
    if res["status_code"] == 200:
        data = res["response"]

    return data


def delete_user(user_id: str):
    res = False
    res = avaturn.delete_user(user_id)
    if not res["status_code"] == 200:
        res = True

    return res


def delete_user_avatar(avatar_id: str, user_id: str):
    res = False
    res = avaturn.delete_user_avatar(user_id, avatar_id)
    if not res["status_code"] == 200:
        res = True

    return res


def get_customication(id: str):
    data = {}
    res = avaturn.get_customization(id)
    if res["status_code"] == 200:
        data = res["response"]

    return data


def generate_avatar_async(
    img_path_front: str,
    img_path_side: str,
    gender: str,
    avaturn_user_id: str,
    fcm_token: str
) -> None:
    """전처리 된 이미지로 아바타 생성 비동기 처리

    :param img_path_front: 전면 이미지 경로
    :param img_path_side: 측면 이미지 경로
    :param gender: 성별
    :param avaturn_user_id: 아바타 사용자 ID
    :param fcm_token: 푸시 알림 토큰
    """
    lambda_name_background = "idolmaster-background"
    payload = {
        "api_alias": os.environ["API_ALIAS"],
        "module": "avatars",
        "function_name": "generate_avatar",
        "body": {
            "img_path_front": img_path_front,
            "img_path_side": img_path_side,
            "gender": gender,
            "avaturn_user_id": avaturn_user_id,
            "fcm_token": fcm_token
        }
    }
    lambda_module.invoke(
        lambda_name_background,
        payload,
        use_alias=True,
        invoke_type="Event"
    )


def get_emotion_retargeting(emotion: str, avatar_file_path: str, gender: str) -> str:
    """아바타 감정표현 리타겟팅 api 호출 결과로 나온 파일 경로 조회

    :param emotion: LLM 감정 응답
    :param avatar_file_path: 아바타 기본 모션 파일 경로
    :param gender: 아바타 gender

    :return: 생성된 감정 모션 파일 경로
    """
    gender = 'female' if gender == 'F' else 'male'
    url = (
        const.URL_RETARGETING[os.environ["AWS_REGION"]]
        + const.RETARGETING_API_MOTION_APPLY_REALTIME
    )
    http = urllib3.PoolManager()
    headers = {"content-type": "application/json; charset=UTF-8"}
    body = json.dumps(
        {
            "emotion": emotion,
            "env_name": os.environ["API_ALIAS"],
            "avatar_file_path": avatar_file_path,
            "gender": gender,
        }
    )
    response = http.request("POST", url, headers=headers, body=body)
    print(
        f"[apply_motion_realtime] statusCode : {response.status}, requestParameters : {body}, responseData : {response.data}"
    )
    data = json.loads(response.data.decode("utf-8"))

    if response.status != 200 or not data["result"]:
        raise Exception("[ERROR] Retargeting API (motionApplyRealtime)")

    return data["output_filepath"]


def list_user_avatars(user_id: str):
    data = {}
    res = avaturn.list_user_avatars(user_id)
    if res["status_code"] == 200:
        data = res["response"]

    return data


def new_avatar(
    user_id: str,
    gender: str,
    image_frontal: dict,
):
    data = {}
    # 아바타 생성 시작
    response = avaturn.new_avatar(user_id)
    print(response["status_code"])
    # 이미지 업로드
    if response["status_code"] == 200:
        upload_data = response["response"]
        avatar_id = upload_data["avatar_id"]
        upload_url = upload_data["upload_url"]
        print(avatar_id)
        print(upload_url)
        # 이미지 전처리
        url = os.environ["IMAGE_PREPROCESSING"] + "/img/preprocessing"
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
                    "cn_img": base64.b64encode(image_frontal["data"]).decode('utf-8'),
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
        response = http.request("POST", url, headers=headers, body=input_data)
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
        s3.upload_file(f'user_images/{utc_now_iso}_front.jpg', image_frontal["data"])
        s3.upload_file(f'user_images/{utc_now_iso}_trans_front.jpg', file_binary_f)
        s3.upload_file(f'user_images/{utc_now_iso}_trans_side.jpg', file_binary_s)
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
        # decoded_data = response.data.decode('utf-8')
        # new_avatar_data = json.loads(decoded_data)
        print(response["status_code"])
        # 세션 불러오기
        if response["status_code"] == 200:
            response = avaturn.new_session(user_id, avatar_id)
            print(response["status_code"])
            if response["status_code"] == 200:
                data = response["response"]
                data["id"] = avatar_id
    return data


def new_session(user_id: str):
    data = {}
    response = avaturn.new_session(user_id)
    if response["status_code"] == 200:
        data = response["response"]

    return data


def preprocess_images_async(img_frontal: dict, gender: str, fcm_token: str) -> None:
    """이미지 전처리를 비동기로 처리

    :param img_frontal: 전면 이미지
        {
            'data': bytes,  # 이미지 데이터
            'filename': str  # 이미지 파일명
        }
    :param gender: 성별
    :param fcm_token: 푸시 알림 토큰
    """
    # 원본 이미지 파일 S3 업로드
    utc_now = time.now()
    utc_now_iso = utc_now.isoformat() + "Z"
    img_file_path = f"user_images/{utc_now_iso}_front.jpg"
    s3.upload_file(img_file_path, img_frontal["data"])

    lambda_name_background = "idolmaster-background"
    payload = {
        "api_alias": os.environ["API_ALIAS"],
        "module": "avatars",
        "function_name": "preprocess_images",
        "body": {
            "image_file_path": img_file_path,
            "gender": gender,
            "fcm_token": fcm_token
        }
    }
    lambda_module.invoke(
        lambda_name_background,
        payload,
        use_alias=True,
        invoke_type="Event"
    )


def render_user_avatar_async(avatar_id: str):
    data = {}
    response = avaturn.render_user_avatar_async(avatar_id)
    if response["status_code"] == 200:
        data = response["response"]

    return data
