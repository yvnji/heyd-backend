import boto3

import const


apigatewaymanagementapi_client = lambda url: boto3.client(
    "apigatewaymanagementapi", endpoint_url=url
)
cognito_client = boto3.client("cognito-idp")
dynamodb_client = boto3.client('dynamodb')
dynamodb_resource = boto3.resource("dynamodb")
dynamodb_resource_KR = boto3.resource("dynamodb", region_name="ap-northeast-2")
lambda_client = boto3.client("lambda")
rekognition_client = boto3.client("rekognition")
s3_client = boto3.client("s3")
secretmanager_client = boto3.session.Session().client(
    service_name="secretsmanager", region_name=const.AWS_REGION_VIRGINIA
)
ssm_client = boto3.client("ssm")
