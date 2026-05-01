from lib.client import secretmanager_client


def get_secret():

    secret_name = "idolmaster/auth"
    get_secret_value_response = secretmanager_client.get_secret_value(
        SecretId=secret_name
    )

    secret = get_secret_value_response["SecretString"]
    return secret
