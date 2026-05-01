import os


AWS_REGION_SEOUL = "ap-northeast-2"
AWS_REGION_VIRGINIA = "us-east-1"

ALIAS_DEV = "dev"
ALIAS_STAGE = "staging"
ALIAS_PROD = "prod"

API_VERSION_PUBLIC = "public"
API_VERSION_V1 = "api"
API_VERSION_V2 = "v2"

AVATAR_TYPE_DEFAULT = "default"

CHARACTER_TYPE_CELEB = "celeb"
CHARACTER_TYPE_CONCEPT = "concept"
CHARACTER_TYPE_MISSION = "mission"
CHARACTER_TYPE_MYSTERY = "mystery"
CHARACTER_TYPE_PRESET = "preset"
CHARACTER_TYPE_USER = "user"

CHAT_TYPE_CHARACTER = "character"
CHAT_TYPE_CONTENT = "content"
CHAT_TYPE_GAME = "game"
CHAT_TYPE_GROUP = "group"
CHAT_TYPE_SHARE = "share"

CLOUDFRONT_DOMAIN = {
    AWS_REGION_SEOUL: {
        ALIAS_DEV: "https://seoul-dev.hey-d.ai",
        ALIAS_STAGE: "https://seoul-staging.hey-d.ai",
    },
    AWS_REGION_VIRGINIA: {
        ALIAS_DEV: "https://dev.hey-d.ai",
        ALIAS_STAGE: "https://staging.hey-d.ai",
        ALIAS_PROD: "https://hey-d.ai",
    },
}

CONTENT_CATEGORY_MAIN = "main"
CONTENT_RATING_ADULT = "18"
CONTENT_RATING_GENERAL = "G"
CONTENT_TYPE_CHATROOM = "chatroom"

CRYPTO_PRIVATE_KEY = "/KEY_FILE/crypto_private_key"

CURRENCY_KR = "KRW"
CURRENCY_US = "USD"

IDENTITY_PROVIDER_APPLE = "apple"
IDENTITY_PROVIDER_COGNITO = "cognito"
IDENTITY_PROVIDER_FACEBOOK = "facebook"
IDENTITY_PROVIDER_FIREBASE = "firebase"
IDENTITY_PROVIDER_GOOGLE = "google"

MISSION_ENDING_BAD = "bad"
MISSION_ENDING_NORMAL = "normal"
MISSION_ENDING_TRUE = "true"

S3_DIRECTORY_GAME_CHAT_BACKGROUND = "game_chat_background"
S3_DIRECTORY_GAME_CHAT_BACKGROUND_DEFAULT = "game_chat_background/default"
S3_DIRECTORY_GAME_CHAT_BGM = "game_chat_bgm"
S3_DIRECTORY_GAME_ENDING_IMAGE = "game_ending_image"
S3_DIRECTORY_GAME_THUMBNAIL = "game_thumbnail"

SHARED_CHATROOM_SALT = "28hvPotZNpXtpeCJxt2aBbVoTAfK9fxxpwR6EqTND3heGDqwAH"

SQL_DB_NAME = "idolmaster"

PLATFORM_GOOGLE_PLAY = "google_play"
PLATFORM_APP_STORE = "app_store"
PLATFORM_PORTONE = "portone"  # PG
PLATFORM_REWARD = "reward"  # 결제가 아닌 보상

PRODUCT_NAME_DART = "dart"
PRODUCT_NAME_GEM = "gem"

PRODUCT_CHARGE_TYPE_DEDUCT_MESSAGE = "deduct_message"
PRODUCT_CHARGE_TYPE_PURCHASE_DART_029 = "purchase_dart_029"
PRODUCT_CHARGE_TYPE_PURCHASE_DART_099 = "purchase_dart_099"
PRODUCT_CHARGE_TYPE_PURCHASE_DART_499 = "purchase_dart_499"
PRODUCT_CHARGE_TYPE_PURCHASE_DART_19900 = "purchase_dart_19900"
PRODUCT_CHARGE_TYPE_PURCHASE_TEMP01 = "purchase_temp01"
PRODUCT_CHARGE_TYPE_PURCHASE_PREMIUM = "premium"
PRODUCT_CHARGE_TYPE_REWARD_DAILY = "reward_daily"
PRODUCT_CHARGE_TYPE_REWARD_SURVEY = "reward_survey"
PRODUCT_CHARGE_TYPE_SIGN_UP = "sign_up"

PRODUCT_AMOUNT_REWARD_DAILY_DART = 30
PRODUCT_AMOUNT_REWARD_DAILY_GEM = 0
PRODUCT_AMOUNT_REWARD_SURVEY_DART = 100
PRODUCT_AMOUNT_REWARD_SURVEY_GEM = 0

PURCHASE_STATUS_PAID = "paid"
PURCHASE_STATUS_REQUEST = "request"

RETARGETING_API_MOTION_APPLY = "api/motionApply"
RETARGETING_API_MOTION_APPLY_REALTIME = "api/motionApplyRealtime"
COMPRESS_AND_SAVE_API = (
    "api/saveCharacterinCompress"  # 아바턴 3D 파일 압축 후 S3 저장 API
)

S3_KEY_CONTENT_BACKGROUND = "content/background"
S3_KEY_CONTENT_BGM = "content/bgm"
S3_KEY_CONTENT_THUMBNAIL = "content/thumbnail"

SURVEY_STATUS_BEFORE_SURVEY = "before_survey"
SURVEY_STATUS_BEFORE_REWARD = "before_reward"
SURVEY_STATUS_REWARDED = "rewarded"

USER_DEACTIVATE_BIRTH_DATE = "9999-12-31"

URL_RETARGETING = {
    # AWS_REGION_VIRGINIA: "http://internal-auto-retargetting-realtime-lb-2102383175.us-east-1.elb.amazonaws.com/",
    AWS_REGION_VIRGINIA: "http://internal-LB-heyd-auto-retargetting-922013098.us-east-1.elb.amazonaws.com/",
    AWS_REGION_SEOUL: "http://internal-LB-auto-retargetting-realtime-1979848867.ap-northeast-2.elb.amazonaws.com/",
}

AVATURN_ACCESS_TOKEN = os.environ["AVATURN_ACCESS_TOKEN"]

APIGATEWAY_MANAGEMENT_API_URL = {
    AWS_REGION_SEOUL: {
        ALIAS_DEV: f"https://{os.environ['WEBSOCKET_API_ID_SEOUL']}.execute-api.ap-northeast-2.amazonaws.com/dev/",
        ALIAS_STAGE: f"https://{os.environ['WEBSOCKET_API_ID_SEOUL']}.execute-api.ap-northeast-2.amazonaws.com/staging/",
    },
    AWS_REGION_VIRGINIA: {
        ALIAS_DEV: f"https://{os.environ['WEBSOCKET_API_ID_VIRGINIA']}.execute-api.us-east-1.amazonaws.com/dev/",
        ALIAS_STAGE: f"https://{os.environ['WEBSOCKET_API_ID_VIRGINIA']}.execute-api.us-east-1.amazonaws.com/staging/",
        ALIAS_PROD: f"https://{os.environ['WEBSOCKET_API_ID_VIRGINIA']}.execute-api.us-east-1.amazonaws.com/prod/",
    },
}

COGNITO_USER_POOL_ID = {
    AWS_REGION_SEOUL: {
        ALIAS_DEV: os.environ["COGNITO_USER_POOL_ID_SEOUL_DEV"],
        ALIAS_STAGE: os.environ["COGNITO_USER_POOL_ID_SEOUL_STAGING"],
    },
    AWS_REGION_VIRGINIA: {
        ALIAS_DEV: "",
        ALIAS_STAGE: "",
        ALIAS_PROD: os.environ["COGNITO_USER_POOL_ID_VIRGINIA"],
    },
}

GCP_API_KEY = os.environ["GCP_API_KEY"]

JWT_ACCESS_TOKEN_EXPIRES_IN = 3600  # 토큰 만료 시간 (1시간)
JWT_ALGORITHM = os.environ["JWT_ALGORITHM"]
JWT_REFRESH_TOKEN_EXPIRES_IN = 7 * 24 * 60 * 60  # 7일
JWT_SECRET_KEY = os.environ["JWT_SECRET_KEY"]

S3_ASSET_CF_DOMAIN = os.environ["S3_ASSET_CF_DOMAIN"]
S3_BUCKET_NAME = {
    AWS_REGION_SEOUL: {
        ALIAS_DEV: f"{os.environ['S3_BUCKET_NAME']}-dev-seoul",
        ALIAS_STAGE: f"{os.environ['S3_BUCKET_NAME']}-staging-seoul",
    },
    AWS_REGION_VIRGINIA: {
        ALIAS_DEV: f"{os.environ['S3_BUCKET_NAME']}-dev",
        ALIAS_STAGE: f"{os.environ['S3_BUCKET_NAME']}-staging",
        ALIAS_PROD: os.environ["S3_BUCKET_NAME"],
    },
}

SQL_DB_HOST = {
    AWS_REGION_SEOUL: {
        ALIAS_DEV: os.environ["SQL_DB_HOST_SEOUL_DEV"],
        ALIAS_STAGE: os.environ["SQL_DB_HOST_SEOUL_STAGING"],
    },
    AWS_REGION_VIRGINIA: {
        ALIAS_DEV: os.environ["SQL_DB_HOST_VIRGINIA_DEV"],
        ALIAS_STAGE: os.environ["SQL_DB_HOST_VIRGINIA_STAGING"],
        ALIAS_PROD: os.environ["SQL_DB_HOST_VIRGINIA_PROD"],
    },
}
SQL_DB_PORT = int(os.environ["SQL_DB_PORT"])
SQL_DB_USER = {
    ALIAS_DEV: os.environ["SQL_DB_USER_DEV"],
    ALIAS_STAGE: os.environ["SQL_DB_USER_STAGING"],
    ALIAS_PROD: os.environ["SQL_DB_USER_PROD"],
}
SQL_DB_PASSWORD = {
    ALIAS_DEV: os.environ["SQL_DB_PASSWORD_DEV"],
    ALIAS_STAGE: os.environ["SQL_DB_PASSWORD_STAGING"],
    ALIAS_PROD: os.environ["SQL_DB_PASSWORD_PROD"],
}

SURVEY_LINK_ID = {
    AWS_REGION_SEOUL: {
        ALIAS_DEV: os.environ["SURVEY_LINK_ID_SEOUL_DEV"],
        ALIAS_STAGE: os.environ["SURVEY_LINK_ID_SEOUL_STAGING"],
    },
    AWS_REGION_VIRGINIA: {
        ALIAS_DEV: os.environ["SURVEY_LINK_ID_VIRGINIA_DEV"],
        ALIAS_STAGE: os.environ["SURVEY_LINK_ID_VIRGINIA_STAGING"],
        ALIAS_PROD: os.environ["SURVEY_LINK_ID_VIRGINIA_PROD"],
    },
}
SURVEY_SHEET_ID = {
    AWS_REGION_SEOUL: {
        ALIAS_DEV: os.environ["SURVEY_SHEET_ID_SEOUL_DEV"],
        ALIAS_STAGE: os.environ["SURVEY_SHEET_ID_SEOUL_STAGING"],
    },
    AWS_REGION_VIRGINIA: {
        ALIAS_DEV: os.environ["SURVEY_SHEET_ID_VIRGINIA_DEV"],
        ALIAS_STAGE: os.environ["SURVEY_SHEET_ID_VIRGINIA_STAGING"],
        ALIAS_PROD: os.environ["SURVEY_SHEET_ID_VIRGINIA_PROD"],
    },
}

# 썸네일 검열 제외 카테고리
# 참고: rekognition 조절 레이블 목록 https://docs.aws.amazon.com/ko_kr/rekognition/latest/dg/moderation.html
EXCLUDED_CATEGORIES = [
    "Bare Back",
    "Exposed Male Nipple",
    "Kissing on the Lips",
    "Female Swimwear or Underwear",
    "Male Swimwear or Underwear",
    "Smoking",
    "Drinking",
    "Alcoholic Beverages",
    "Gambling",
    "Drugs & Tobacco",
    "Drugs & Tobacco Paraphernalia & Use",
    "Swimwear or Underwear",
    "Alcohol",
]
