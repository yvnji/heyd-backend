from datetime import datetime
from datetime import timezone
from dateutil import tz
from decimal import Decimal
from zoneinfo import ZoneInfo


tz_utc = timezone.utc
tz_ko = tz.gettz("Asia/Seoul")


def fromtimestamp(ts, tz=None):
    """timestamp를 입력받아 datatime 형태로 바꿔주는 함수

    :param timestamp ts: timestamp
    :param tz: timezone

    :return datetime: datetime 형태로 변환된 결과

    """
    return datetime.fromtimestamp(ts, tz=tz)


def now(tz=None):
    """현재의 datetime 리턴하는 함수

    :param tz: timezone

    :return 현재의 datetime

    """
    return datetime.now(tz=tz)


def timezone_info(tz_iana=None):
    """시간대의 이름으로 timezone 객체 반환
    IANA 시간대를 기준으로 한다.

    :param str tz_iana: 시간대 이름

        e.g.
            - Asia/Seoul
            - America/New_York

    :return timezone
    """
    tz_iana = tz_iana if tz_iana else "UTC"
    return ZoneInfo(tz_iana)


def timestampnow(tz=None):
    """현재의 timestamp 리턴하는 함수

    :return timestamp: 현재의 timestamp

    """
    return round(Decimal(now().timestamp()), 3)


def totimestamp(dt: datetime) -> Decimal:
    """datetime -> timestamp

    :param dt: datetime

    :return: 소수점 3자리 수 Decimal timestamp
    """
    return round(Decimal(dt.timestamp()), 3)
