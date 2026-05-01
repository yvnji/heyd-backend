import os

import pymysql
import pymysql.cursors

import const


def get_db_connection():
    region = os.environ["AWS_REGION"]
    api_alias = os.environ["API_ALIAS"]
    return pymysql.connect(
        host=const.SQL_DB_HOST[region][api_alias],
        user=const.SQL_DB_USER[api_alias],
        port=const.SQL_DB_PORT,
        password=const.SQL_DB_PASSWORD[api_alias],
        database=const.SQL_DB_NAME,
        autocommit=False,
        cursorclass=pymysql.cursors.DictCursor,
    )
