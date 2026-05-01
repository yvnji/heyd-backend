import os

import const
from lib.decorator import mandatory_params
from lib.exception import IdolmasterBadRequestException
from lib.exception import IdolmasterConflictResourceException
from lib.exception import IdolmasterResourceNotFoundExeption
from service import avatar as avatar_module
from service import character as character_module
from service import user as user_module
from thirdparty import s3


@mandatory_params(["avatars"])
def delete_avatars(event, context, params):
    """사용자가 소유한 아바타 삭제
    character.delete_delete_avatar 수정
    parameter avaturn_id -> path parameter avatars 수정
    """
    email = event["requestContext"]["authorizer"]["email"]
    avatar_id = params["avatars"]

    # avaturn_id 확인
    if not character_module.get_avatar(avatar_id, email=email):
        raise IdolmasterResourceNotFoundExeption(message="ID not found")

    character_module.delete_avatar(avatar_id)


def get_avatars(event, context, params):
    """사용자가 조회 가능한 아바타 모두 조회 (생성 + 복사)
    character.post_get_avatar, character.post_list_avatar 통합
    return은 post_get_avatar 포맷 사용
    return avaturn_id -> avatar_id
    """
    email = event["requestContext"]["authorizer"]["email"]
    avatar_type = params.get("type")

    # type 확인
    if avatar_type and avatar_type not in ("default"):
        raise IdolmasterBadRequestException(message="Invalid type", result_code=1)

    avatar_list = character_module.list_avatar(email=email, avatar_type=avatar_type)
    return {
        "data": [
            {
                "file": a["file"],
                "thumbnail": a["thumbnail"],
                "avatar_id": a["avaturn_id"],
                "type": a["type"],
                "gender": a["gender"]
            }
            for a in avatar_list
        ]
    }


@mandatory_params(["avaturn_id", "model_file_path", "thumbnail_file", "gender"])
def post_avatars(event, context, body):
    """아바턴 API를 통해 생성한 아바타의 정보를 DB에 저장
    character.post_save_avatar 수정
    """
    email = event["requestContext"]["authorizer"]["email"]
    avatar_id = body["avaturn_id"]
    model_file_path = body["model_file_path"]
    gender = body["gender"]
    img_file = body.get("thumbnail_file")
    img_file_path = ""

    # avaturn_id 확인
    if character_module.get_avatar(avatar_id):
        raise IdolmasterConflictResourceException("Conflict avaturn_id")

    # 썸네일 파일 저장
    if img_file:
        img_file_path = character_module.put_thumbnail_s3(img_file["data"])

    res = avatar_module.render_user_avatar_async(avatar_id)
    print("render complete", res)
    character_module.save_avatar(
        email,
        avatar_id,
        model_file_path,
        img_file_path,
        gender,
    )


#######################################################
# path 시작이 /avatars/ 아닌 API
#######################################################


@mandatory_params(["fcm_token", "image_frontal", "gender"])
def post_avatars_preprocessing_images(event, context, body):
    """아바타 생성 전 이미지 전처리"""
    user_id = int(event["requestContext"]["authorizer"]["db_id"])
    img_frontal = body["image_frontal"]
    fcm_token = body["fcm_token"]
    gender = body["gender"].lower()

    # check params
    try:
        param_name = "fcm_token"
        assert user_module.validate_fcm_token(fcm_token, user_id)   # fcm_token 유효성 검사
        param_name = "gender"
        assert gender in ("male", "female")
    except AssertionError:
        raise IdolmasterBadRequestException(message=f"Invalid {param_name}", result_code=1)

    # 이미지 전처리
    avatar_module.preprocess_images_async(img_frontal, gender, fcm_token)


@mandatory_params([
    "fcm_token",
    "image_path_frontal",
    "image_path_side",
    "gender",
    "user_id"
])
def post_avatars_generating(event, context, body):
    """전처리 된 이미지로 아바타 생성"""
    user_id = int(event["requestContext"]["authorizer"]["db_id"])
    fcm_token = body["fcm_token"]
    img_path_front = body["image_path_frontal"].strip("/")
    img_path_side = body["image_path_side"].strip("/")
    gender = body["gender"].lower()
    avaturn_user_id = body["user_id"]

    # check params
    try:
        param_name = "fcm_token"
        assert user_module.validate_fcm_token(fcm_token, user_id)   # fcm_token 유효성 검사
        param_name = "gender"
        assert gender in ("male", "female")
    except AssertionError:
        raise IdolmasterBadRequestException(message=f"Invalid {param_name}", result_code=1)

    # 이미지 파일 존재 확인
    bucket_name = const.S3_BUCKET_NAME[os.environ["AWS_REGION"]][
        os.environ["API_ALIAS"]
    ]
    try:
        param_name = "image_path_frontal"
        s3.check_object(bucket_name, img_path_front)
        param_name = "image_path_side"
        s3.check_object(bucket_name, img_path_side)
    except IdolmasterResourceNotFoundExeption:
        raise IdolmasterResourceNotFoundExeption(message=f"{param_name} not found")

    avatar_module.generate_avatar_async(
        img_path_front,
        img_path_side,
        gender,
        avaturn_user_id,
        fcm_token
    )
