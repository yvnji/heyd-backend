import os

import pymysql
import pymysql.cursors

import const


def get_db_connection(stage):
    region = os.environ["AWS_REGION"]
    return pymysql.connect(
        host=const.SQL_DB_HOST[region][stage],
        user=const.SQL_DB_USER[stage],
        port=const.SQL_DB_PORT,
        password=const.SQL_DB_PASSWORD[stage],
        database=const.SQL_DB_NAME,
        autocommit=False,
        cursorclass=pymysql.cursors.DictCursor,
    )
