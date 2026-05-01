import os
import traceback
from datetime import timedelta
from decimal import Decimal

from boto3.dynamodb.conditions import Key

import const
from lib import http_request
from lib import time
from lib.decorator import preprocessing_cursor
from service import user as user_module
from thirdparty import dynamodb
from thirdparty.mariadb import get_db_connection


@preprocessing_cursor
def access_product(
    email: str, platform: str, charge_type: str, cursor: object = None
) -> None:
    """상품 구매에 접근한 시간 업데이트

    :param email: email
    :param platform: 결제 플랫폼
    :param charge_type: 충전 유형
    :param cursor: pymysql.connect().cursor()
    """
    query = f"""
    SELECT id
    FROM `user_product_expiration`
    WHERE
        email = '{email}'
        AND charge_type = '{charge_type}'
        AND platform = '{platform}'
        AND purchase_status = '{const.PURCHASE_STATUS_REQUEST}'
    """
    cursor.execute(query)
    item = cursor.fetchone()

    if item:
        query = f"""
        UPDATE `user_product_expiration`
        SET
            created_at = CURRENT_TIMESTAMP(),
            updated_at = CURRENT_TIMESTAMP()
        WHERE
            id = {item["id"]}
        """
    else:
        expiration_at = get_expiration_utc(charge_type)
        expiration_utc = expiration_at.astimezone(time.tz_utc).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        query = f"""
        INSERT INTO `user_product_expiration` (email, charge_type, platform, expiration_utc, purchase_status)
        VALUES ('{email}', '{charge_type}', '{platform}', '{expiration_utc}', '{const.PURCHASE_STATUS_REQUEST}')
        """

    cursor.execute(query)


def charge_product_expiration(
    email: str,
    charge_type: str,
    dart: int,
    gem: int,
    expiration: time.datetime,
    platform: str = const.PLATFORM_REWARD,
) -> bool:
    """유효기간이 있는 다트/젬 보상 충전

    :param email: email
    :param charge_type: 충전 유형 ('reward_daily', 'reward_survey')
    :param dart: 충전 다트
    :param gem: 충전 젬
    :param expiration: 유효기간
    :param platform: 결제 플랫폼

    :return
        True : 충전 성공
        False : 충전 실패
    """
    if not dart and not gem:
        print(f"There are no products to charge (charge_type : {charge_type})")
        return True

    # 프리미엄 구독
    if charge_type == const.PRODUCT_CHARGE_TYPE_PURCHASE_DART_19900:
        user_module.subscribe_premium(email)

    db_connection = get_db_connection()
    expiration_utc = expiration.astimezone(time.tz_utc).strftime(
        "%Y-%m-%d %H:%M:%S"
    )  # UTC 시간

    with db_connection as db:
        cursor = db.cursor()

        # request 상태 확인
        query = f"""
        SELECT id
        FROM `user_product_expiration`
        WHERE
            email = '{email}'
            AND charge_type = '{charge_type}'
            AND platform = '{platform}'
            AND purchase_status = '{const.PURCHASE_STATUS_REQUEST}'
        """
        cursor.execute(query)
        item_request = cursor.fetchone()

        try:
            product_id = None
            if item_request:
                product_id = item_request["id"]
                update_query = f"""
                UPDATE `user_product_expiration`
                SET
                    purchase_status = '{const.PURCHASE_STATUS_PAID}',
                    expiration_utc = '{expiration_utc}',
                    dart = {dart},
                    gem = {gem}
                WHERE
                    id = {product_id}
                """
                cursor.execute(update_query)

            else:
                insert_query = f"""
                    INSERT INTO `user_product_expiration` (
                        email, charge_type, dart, gem, expiration_utc, platform, purchase_status
                    )
                    VALUES (
                        '{email}', '{charge_type}',
                        {dart}, {gem},
                        '{expiration_utc}', '{platform}',
                        '{const.PURCHASE_STATUS_PAID}'
                    )
                    ON DUPLICATE KEY UPDATE expiration_utc = '{expiration_utc}'
                    RETURNING id
                """
                cursor.execute(insert_query)
                latest_id = cursor.fetchone()["id"]

                select_query = f"""
                    SELECT * FROM `user_product_expiration` WHERE id = {latest_id}
                """
                cursor.execute(select_query)
                product_id = cursor.fetchone()["id"]

            # 유효기간 지난 다트/젬 모두 삭제
            # delete_query = f"DELETE FROM `user_product_expiration` WHERE email = '{email}' AND expiration_utc < NOW()"
            # cursor.execute(delete_query)

            db.commit()

            # 충전 이력 저장
            dynamodb.put_item("idolmaster_history_product", {
                "email": email,
                "timestamp_at": round(time.timestampnow(), 5),
                "product_expiration_id": product_id,
                "charge_type": charge_type,
                "dart": dart,
                "gem": gem,
            })

            return True
        except Exception:
            traceback.print_exc()
            return False


def check_key(key: str) -> bool:
    """충전 Key 확인

    :param key: key

    :return: key 확인 결과
    """
    ret = False
    table_name = "idolmaster_key_temporary"
    key_data = dynamodb.fetch_data_query(
        table_name,
        Key("uuid").eq(key)
    )[0]
    if key_data and not key_data[0]["used"]:
        dynamodb.put_item(table_name, {
            "uuid": key,
            "created_at": key_data[0]["created_at"],
            "used_at": time.timestampnow(),
            "used": True
        })
        ret = True
    return ret


def check_survey(email: str) -> bool:
    """설문 완료 여부 확인

    :param email: email

    :return
        True : 설문 완료
        False : 설문 x
    """
    ret = False
    api_key = const.GCP_API_KEY
    spread_sheet_id = const.SURVEY_SHEET_ID[os.environ["AWS_REGION"]][
        os.environ["API_ALIAS"]
    ]
    sheet_range = "설문지 응답 시트1!B:B"
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{spread_sheet_id}/values/{sheet_range}?key={api_key}"
    response = http_request.request("GET", url)

    if "error" in response["response"]:
        print(f"Google Sheets API error: {response['response']['error']}")
        return False

    if "values" in response["response"]:
        values = response["response"]["values"]
        if [email] in values:
            ret = True

    return ret


@preprocessing_cursor
def decrease_product(email: str, deduct_type: str, cursor: object = None):
    """종류에 따른 다트/젬 차감

    :param email: email
    :param deduct_type: product_charge_type 테이블에 저장되어 있는 충전 타입 중 차감 타입 이름
        e.g. deduct_message
    :param cursor: pymysql.connect().cursor()

    :return
        {
            'result': bool,
                True : 차감 성공
                False : 차감 실패
            'remain': {
                'dart': int,
                'gem': int
            }
        }
    """
    ret = {"result": False, "remain": {"dart": 0, "gem": 0}}

    # 남아있는 다트/젬 조회
    check_query = f"""
        SELECT id, dart, gem
        FROM `user_product_expiration`
        WHERE
            email = '{email}'
            AND expiration_utc > NOW()
            AND dart + gem > 0
        ORDER BY expiration_utc, id
    """
    cursor.execute(check_query)
    data_list = cursor.fetchall()
    for d in data_list:
        ret["remain"]["dart"] += d["dart"]
        ret["remain"]["gem"] += d["gem"]

    # 차감 수량 조회
    deduct_ammount_query = f"""
        SELECT dart, gem
        FROM `product_charge_type`
        WHERE name = '{deduct_type}'
    """
    cursor.execute(deduct_ammount_query)
    deduct_item = cursor.fetchone()

    # 다트/젬 차감
    if (
        -deduct_item["dart"] <= ret["remain"]["dart"]
        and -deduct_item["gem"] <= ret["remain"]["gem"]
    ):
        dart_require = -deduct_item["dart"]
        gem_require = -deduct_item["gem"]
        for data_at in data_list:
            dart_at = dart_require
            gem_at = gem_require
            if data_at["dart"] < dart_require:
                dart_at = data_at["dart"]
            if data_at["gem"] < gem_require:
                gem_at = data_at["gem"]
            dart_require -= dart_at
            gem_require -= gem_at
            update_query = f"""
                UPDATE `user_product_expiration`
                SET
                    dart = dart - {dart_at},
                    gem = gem - {gem_at}
                WHERE
                    id = {data_at['id']}
            """
            cursor.execute(update_query)

            # 차감 이력 저장
            dynamodb.put_item("idolmaster_history_product", {
                "email": email,
                "timestamp_at": round(Decimal(time.timestampnow()), 5),
                "product_expiration_id": data_at["id"],
                "charge_type": deduct_type,
                "dart": int(-dart_at),
                "gem": int(-gem_at),
            })

            if dart_require or gem_require:
                continue
            else:
                break
        ret["result"] = True
        ret["remain"]["dart"] += deduct_item["dart"]
        ret["remain"]["gem"] += deduct_item["gem"]
    else:
        print("deduct fail")

    return ret


@preprocessing_cursor
def dict_products(platform: str, cursor: object = None) -> dict:
    """결제 플랫폼에 등록된 제품들의 정보 조회

    :param platform: 결제 플랫폼 (google_play, app_store, portone)
    :param cursor: pymysql.connect().cursor()

    :return
        {
            '{product_id}': {
                'price': Decimal,
                'dart': int,
                'gem': int,
                'charge_type': str
            },
            ...
        }
    """
    if platform in [const.PLATFORM_APP_STORE, const.PLATFORM_GOOGLE_PLAY]:
        query = """
        SELECT
            name,
            dart,
            gem,
            price,
            product_id
        FROM
            `product_charge_type`
        WHERE
            product_id IS NOT NULL
        """
        cursor.execute(query)
        products = cursor.fetchall()
        return {
            p["product_id"]: {
                "price": p["price"],
                "dart": p["dart"],
                "gem": p["gem"],
                "charge_type": p["name"],
            }
            for p in products
        }

    # Temporary for test
    elif platform == const.PLATFORM_PORTONE:
        return {
            "temp01": {
                "price": Decimal("1"),
                "dart": 10,
                "gem": 0,
                "charge_type": const.PRODUCT_CHARGE_TYPE_PURCHASE_TEMP01,
            }
        }


def get_expiration_utc(charge_type: str, timezone_iana: str = None) -> time.datetime:
    """제품 종류 별 유효기간 조회 (UTC 기준)

    :param charge_type: 충전 유형
    :param timezone_iana: IANA 시간대

    :return: 유효기간 datetime
    """
    expiration_at = time.now() + timedelta(days=365 * 100)
    timezone_iana = timezone_iana if timezone_iana else None
    daily_type = (const.PRODUCT_CHARGE_TYPE_REWARD_DAILY, const.PRODUCT_CHARGE_TYPE_PURCHASE_DART_029)
    if charge_type in daily_type:
        expiration_at = time.now(time.timezone_info(timezone_iana)).replace(
            hour=23, minute=59, second=59
        )
    return expiration_at


def get_product(email: str) -> dict:
    """다트/젬 조회

    :param email: email

    :return
        {
            'dart': {integer},
            'gem': {integer}
        }
    """
    db_connection = get_db_connection()
    res = None
    query = """
        SELECT
            COALESCE(SUM(dart), 0) AS dart,
            COALESCE(SUM(gem), 0) AS gem
        FROM
            `user_product_expiration`
        WHERE
            email = %s
            AND purchase_status = %s
            AND expiration_utc > NOW()
        GROUP BY
            email
    """
    with db_connection.cursor() as cursor:
        cursor.execute(query, (email, const.PURCHASE_STATUS_PAID))
        res = cursor.fetchone()
    return {
        "dart": int(res["dart"]) if res else 0,
        "gem": int(res["gem"]) if res else 0,
    }


def get_survey_link(email: str) -> str:
    """Email이 들어간 설문 링크 조회"""
    survey_id = const.SURVEY_LINK_ID[os.environ["AWS_REGION"]][os.environ["API_ALIAS"]]
    return f"https://docs.google.com/forms/d/e/{survey_id}/viewform?usp=pp_url&entry.652685006={email}"


def list_charge_type(name: str = None) -> list:
    """보상 타입 조회

    :param name: 조회할 타입 이름 (e.g. reward_daily, reward_survey)

    :return
        [
            {
                'name': str,
                'description': str,
                'dart': int,
                'gem': int
            },
            ...
        ]
    """
    where_name = f"WHERE name = '{name}'" if name else ""
    query = f"""
        SELECT
            name, description, dart, gem
        FROM
            `product_charge_type`
        {where_name}
        ORDER BY name
    """
    db_connection = get_db_connection()
    with db_connection.cursor() as cursor:
        cursor.execute(query)
        return cursor.fetchall()


@preprocessing_cursor
def list_charge_type_v2(cursor: object = None) -> list:
    """제품 타입 조회

    :return
        [
            {
                'title': str,
                'name': str,
                'description': str,
                'price': Decimal,
                'product_id': str,
                'dart': int,
                'gem': int
            },
            ...
        ]
    """
    query = """
    SELECT
        id,
        title,
        name,
        description,
        product_id,
        price,
        dart,
        gem
    FROM `product_charge_type`
    WHERE title IS NOT NULL
    """
    cursor.execute(query)
    return cursor.fetchall()


def list_product_expiration(
    email: str,
    charge_type: str = None,
    expiration_utc: time.datetime = None,
    ascending: bool = True,
    limit: int = 50,
):
    """유효기간 있는 다트/젬 리스트 조회.

    :param email: email
    :param charge_type: 충전 타입. 값이 없을 경우 모든 데이터 조회
        e.g. reward_daily, reward_survey
    :param expiration_utc: 유효기간. 값이 없을 경우 모든 데이터 조회
    :param ascending: 유효기간 정렬 기준
        True : 오름차순
        False : 내림차순
    :param limit: 조회할 데이터 최대 수

    :return
        [
            {
                'gem': int,
                'dart': int,
                'charge_type': str,
                'expiration_utc': datetime
            },
            ...
        ]
    """
    sort = "ASC" if ascending else "DESC"
    where_charge_type = f"AND charge_type = '{charge_type}'" if charge_type else ""
    where_expiration_utc = ""

    if expiration_utc:
        expiration_at = expiration_utc.astimezone(time.tz_utc).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        where_expiration_utc = f"AND expiration_utc = '{expiration_at}'"

    query = f"""
        SELECT
            gem, dart, charge_type, expiration_utc
        FROM
            `user_product_expiration`
        WHERE
            email = '{email}'
            {where_charge_type}
            {where_expiration_utc}
        ORDER BY expiration_utc {sort}
        LIMIT {limit}
    """
    db_connection = get_db_connection()
    with db_connection.cursor() as cursor:
        cursor.execute(query)
        return cursor.fetchall()
