import json
import urllib3


def request(method: str, url: str, headers: dict = None, data: dict = None) -> dict:
    """http 요청 모듈

    :param method : HTTP Method
    :param url : request URL
    :param headers : request header
    :param data
        - method in ['POST', 'PUT'] : request body
        - method in ['DELETE', 'GET'] : request parameters

    :return
        {
            'status_code': int
            'response' : response object
        }
    """
    http = urllib3.PoolManager()
    method = method.upper()
    if method in ["POST", "PUT"]:
        if data and not isinstance(data, bytes):
            data = json.dumps(data)
        res = http.request(method, url, headers=headers, body=data)
    else:
        res = http.request(method, url, headers=headers, fields=data)
    res_data = res.data
    print(f"[HTTP Requst] method : {method}, url : {url}, statusCode : {res.status}, data : {res_data}")
    response = {
        "status_code": res.status,
        "response": json.loads(res_data.decode("utf-8")) if res_data else None,
    }
    return response
