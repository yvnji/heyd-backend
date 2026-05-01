from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding

import const
from lib.client import ssm_client


def rsa_signer(message):
    res = ssm_client.get_parameter(
        Name=const.CRYPTO_PRIVATE_KEY,
        WithDecryption=True
    )
    private_key = serialization.load_pem_private_key(
        bytes(res["Parameter"]["Value"], "utf-8"),
        password=None,
        backend=default_backend()
    )
    return private_key.sign(message, padding.PKCS1v15(), hashes.SHA1())
