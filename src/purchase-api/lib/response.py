import json


def get_status_code(result_code: int) -> int:
    """result code에 따라 정의된 http status code 반환
    참고 : https://www.notion.so/HTTP-dbb9e11709c44df9b7b119d886f7d8b8
    """
    result_code_dict = {
        "1": 200,  # 성공
        "101": 401,  # API키 오류(불일치)
        "102": 401,  # API키 누락
        "103": 401,  # 토큰 오류(불일치)
        "104": 401,  # 토큰 누락
        "105": 401,  # 토큰 만료
        "106": 401,  # 토큰 권한 없음
        "107": 400,  # 항목의 데이터 길이 오류
        "108": 400,  # 필수 항목 누락
        "109": 400,  # 데이터 포맷 오류
        "110": 500,  # 네트워크 오류
        "111": 403,  # 조회 권한 오류
        "112": 500,  # 내부 오류
        "113": 400,  # 전송시간 오류(sendDate)
        "114": 400,  # 해당유저 없음(clientKey)
        "115": 400,  # 존재하지 않는 채팅방
        "116": 400,  # WEBRTC 값 오류
        "117": 400,  # 최대 유저수 초과
        "118": 429,  # 너무 많은 요청
        "119": 400,  # 해당 계정 요금제 만료
        "120": 400,  # 존재하지 않는 스케줄 ID
        "121": 400,  # 채팅방 상태 값 오류
        "122": 400,  # STAT값 오류
        "123": 400,  # 채팅방 유형 오류
        "124": 400,  # 해상도 값 오류
        "125": 400,  # Google Api Key 오류
        "0": 500,  # 정의되지 않은 오류(서비스, 실패)
    }
    return result_code_dict[str(result_code)]


def response_lambda(result_code: int, body: dict = {}, headers: dict = {}) -> dict:
    headers_cors = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "DELETE,GET,HEAD,OPTIONS,PATCH,POST,PUT",
        "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
    }
    body["result"] = result_code
    return {
        "statusCode": get_status_code(result_code),
        "headers": {**headers_cors, **headers},
        "body": json.dumps(body),
    }
