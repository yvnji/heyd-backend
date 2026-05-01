import os


ALIAS_DEV = "dev"
ALIAS_STAGE = "staging"
ALIAS_PROD = "prod"

PRODUCT_NAME_DART = "dart"
PRODUCT_NAME_GEM = "gem"

ANDROID_DEVELOPER_API = "androidpublisher"
ANDROID_DEVELOPER_API_URL = "https://www.googleapis.com/auth/androidpublisher"
ANDROID_DEVELOPER_API_VERSION = "v3"

IOS_VERIFICATION_API_URL_PRODUCTION = (
    "https://buy.itunes.apple.com/verifyReceipt"  # PRODUCTION_URL
)
IOS_VERIFICATION_API_URL_SANDBOX = (
    "https://sandbox.itunes.apple.com/verifyReceipt"  # SANDBOX_URL
)

PLATFORM_GOOGLE_PLAY = "google_play"
PLATFORM_APP_STORE = "app_store"
PLATFORM_PORTONE = "portone"  # PG

PORTONE_KEY = os.environ["PORTONE_API_KEY"]
PORTONE_SECRET_KEY = os.environ["PORTONE_SECRET_KEY"]
PORTONE_API_URL = "https://api.iamport.kr"  # V1
PORTONE_API_GET_TOKEN = "/users/getToken"
PORTONE_API_PAYMENTS = "/payments/"

# TODO 플랫폼에 제품 등록 후 db에 저장 필요
PRODUCT_PRICE = {
    "dart_029": "0.29",
    "dart_099": "0.99",
    "dart_499": "4.99",
    "dart_19900": "199",
    "premium": "9.99",
    "temp01": "1000",
}

PURCHASE_STATUS_SUCCESS = "success"
PURCHASE_STATUS_CANCELED = "canceled"
PURCHASE_STATUS_FAILED = "failed"
PURCHASE_STATUS_TEST = "test"
PURCHASE_STATUS_UNKNOWN = "unknown"
