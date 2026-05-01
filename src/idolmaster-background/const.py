import os


AWS_REGION_SEOUL = "ap-northeast-2"
AWS_REGION_VIRGINIA = "us-east-1"

ALIAS_DEV = "dev"
ALIAS_STAGE = "staging"
ALIAS_PROD = "prod"

AVATURN_API_URL = "https://api.avaturn.me/api/v1"
AVATURN_GENERATE_AVATAR_TIMEOUT = 100

IMAGE_PREPROCESSING_TIMEOUT = 180

# Parameter Store
AVATURN_ACCESS_TOKEN = os.environ["AVATURN_ACCESS_TOKEN"]

IMAGE_PREPROCESSING_URL = os.environ["IMAGE_PREPROCESSING"] + "/img/preprocessing"

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
