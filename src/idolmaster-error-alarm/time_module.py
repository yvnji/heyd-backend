from datetime import datetime
from dateutil import tz


# timezone for Seoul
tz_ko = tz.gettz("Asia/Seoul")


def fromtimestamp(ts, tz=None):
    """timestamp를 입력받아 datatime 형태로 바꿔주는 함수

    :param timestamp ts: timestamp
    :param tz: timezone

    :return datetime: datetime 형태로 변환된 결과

    """
    return datetime.fromtimestamp(ts, tz=tz)
