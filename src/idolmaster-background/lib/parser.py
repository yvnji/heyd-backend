import base64

from requests_toolbelt.multipart import decoder


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
