import base64
import json
import re
from decimal import Decimal
from pathlib import Path

from requests_toolbelt.multipart import decoder


def camel_to_snake(name):
    """camelCase -> snake_case"""
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def check_ban(sentence: str, categories: list = None) -> dict:
    """문장 내의 사용 금지 단어 확인

    :param sentence: 확인 할 문장
    :param categories: 금지할 단어 카테고리 (None 일 경우 모든 카테고리 적용)

    :return
        {
            'possibility': bool,   # 사용 가능 여부
            'ban_list': lit   # 문장에 포함되어 있는 금지어 리스트
        }
    """
    ban_folder = "ban_word"
    folder_path = Path(ban_folder)
    ban_list = []
    for file_path in folder_path.iterdir():
        filter_list = []
        file_name = str(file_path).split("/")[-1].split(".")[0]
        if categories and file_name not in categories:
            continue
        with open(file_path) as f:
            filter_list += [line.strip() for line in f.readlines() if line.strip()]
        pattern = rf"{'|'.join(filter_list)}"
        matches = re.findall(pattern, sentence, flags=re.IGNORECASE)
        ban_list += matches
        if matches:
            print(f"[Ban] category : {file_name}, ban list : {matches}")
    return {
        "possibility": not ban_list,
        "ban_list": ban_list
    }


def convert_to_bool(value) -> bool:
    """문자열을 Boolean 값으로 변환"""
    if isinstance(value, bool):
        return value
    elif isinstance(value, str):
        return json.loads(value.lower())
    elif isinstance(value, int) and value in (0, 1):
        return bool(value)
    else:
        raise ValueError


def decimal_encoder(obj):
    """Decimal을 JSON 호환 형식으로 변환"""
    if isinstance(obj, Decimal):
        obj = str(obj)
    return obj


def encode_multipart_form_data(body: bytes, content_type: str) -> dict:
    """multipart/form-data -> dictionary

    :param body: multipart/form-data 형태의 body
    :param content_type: Content-Type

    :return: {key} -> name에 해당하는 Content-Disposition value, {key_another} -> name 해당하지 않는 Content-Disposition value
        {
            '{key}': str,  (Content-Disposition의 content-type이 text일 경우의 content 값)
            '{key}': {     (Content-Disposition의 content-type이 text가 아닐 경우)
                'data': bytes,  (content 값)
                '{key_another}': str
            },
            ...
        }
    """
    body_decoded = base64.b64decode(body)
    item = {}

    # multipart 데이터 파싱
    multipart_data = decoder.MultipartDecoder(body_decoded, content_type)
    for part in multipart_data.parts:
        disposition_item = {}
        headers = part.headers
        content_disposition = headers[
            b"Content-Disposition"
        ].decode()  # 'form-data; name="type"'
        content_disposition_type = headers.get(
            b"Content-Type", b"text"
        )  # e.g. text/xml, image/jpeg
        data = part.content  # 데이터 값

        # key 값 추출
        key_list = content_disposition.split(";")[1:]
        for k in key_list:
            k = k.strip().replace('"', "").split("=")
            disposition_item[k[0]] = k[1]

        # value 추출
        if "text" in content_disposition_type.decode():
            item[disposition_item["name"]] = data.decode()

        # content-type이 text가 아닐 경우, value 변경
        else:
            key = disposition_item["name"]
            item[key] = {}
            for k in disposition_item:
                if not k == "name":
                    item[key][k] = disposition_item[k]
            item[key]["data"] = data

    return item
