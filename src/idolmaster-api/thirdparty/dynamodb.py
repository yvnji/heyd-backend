import json
import os
import traceback
from decimal import Decimal

import botocore

import const
from lib.client import dynamodb_client
from lib.client import dynamodb_resource, dynamodb_resource_KR


def get_resource_obj_KR(table_name: str, alias_pre: bool = True) -> str:
    """boto3 DynamoDB resource 객체 반환"""

    # 배포 환경에 따른 DynamoDB Table 이름
    if alias_pre:
        table_name_pre = (
            ""
            if os.environ["API_ALIAS"] == const.ALIAS_PROD
            else "%s_" % os.environ["API_ALIAS"]
        )
    else:
        table_name_pre = ""
    table_name = f"{table_name_pre}{table_name}"

    return dynamodb_resource_KR.Table(table_name)


def get_resource_obj(table_name: str, alias_pre: bool = True) -> str:
    """boto3 DynamoDB resource 객체 반환"""
    if alias_pre:
        table_name = get_table_name_deployed(table_name)
    return dynamodb_resource.Table(table_name)


def get_table_name_deployed(table_name: str) -> str:
    """배포 버전에 따른 테이블 이름 조회"""
    table_name_pre = (
        ""
        if os.environ["API_ALIAS"] == const.ALIAS_PROD
        else "%s_" % os.environ["API_ALIAS"]
    )
    return table_name_pre + table_name


def get_table_schema(table_name: str) -> dict:
    """DynamoDB 테이블의 스키마 정보를 조회합니다.
    필요한 키만 조회

    Args:
        table_name (str): 테이블 이름

    Returns:
        Dict[str, str]: 테이블 스키마 정보
            {
                "{key_name}": "{key_type}"   # "S", "N", "B"
            }
    """
    response = dynamodb_client.describe_table(TableName=table_name)
    table_info = response["Table"]

    # 파티션 키와 정렬 키 정보 추출
    key_schema = table_info["KeySchema"]
    attribute_definitions = table_info["AttributeDefinitions"]

    # 보조 인덱스 정보 추출
    global_secondary_indexes = table_info.get("GlobalSecondaryIndexes", [])
    local_secondary_indexes = table_info.get("LocalSecondaryIndexes", [])

    # 결과 구성
    schema_info = {}

    # 파티션 키와 정렬 키 정보 설정
    for key in key_schema:
        key_name = key["AttributeName"]
        # key_type = key["KeyType"]  # "HASH" or "RANGE"

        # 해당 키의 데이터 타입 찾기
        for attr in attribute_definitions:
            if attr["AttributeName"] == key_name:
                schema_info[key_name] = attr["AttributeType"]   # "S", "N", "B"

    # 보조 인덱스 정보 설정
    for gsi in global_secondary_indexes:
        for key in gsi["KeySchema"]:
            key_name = key["AttributeName"]

            # 해당 키의 데이터 타입 찾기
            for attr in attribute_definitions:
                if attr["AttributeName"] == key_name:
                    schema_info[key_name] = attr["AttributeType"]

    # 로컬 보조 인덱스 정보 설정
    for lsi in local_secondary_indexes:
        for key in lsi["KeySchema"]:
            key_name = key["AttributeName"]

            # 해당 키의 데이터 타입 찾기
            for attr in attribute_definitions:
                if attr["AttributeName"] == key_name:
                    schema_info[key_name] = attr["AttributeType"]

    return schema_info


def get_total_count(table):
    response = table.scan(Select="COUNT")
    return response["Count"]


def fetch_data_query(
    table_name,
    key,
    scan_condition=None,
    index_name=None,
    projection_exp=None,
    limit=50,
    index_forward=True,
    last_evaluated_key=None
):
    """dynamodb query 데이터 페이징"""
    table = get_resource_obj(table_name)
    query_params = {
        "KeyConditionExpression": key,
        "Limit": limit,
        "ScanIndexForward": index_forward
    }

    if isinstance(last_evaluated_key, str):
        last_evaluated_key = json.loads(last_evaluated_key)
    if last_evaluated_key:
        table_schema = get_table_schema(get_table_name_deployed(table_name))
        for key in last_evaluated_key.keys():
            if table_schema[key] == "N":
                last_evaluated_key[key] = Decimal(str(last_evaluated_key[key]))
            elif table_schema[key] == "S":
                last_evaluated_key[key] = str(last_evaluated_key[key])
            # elif table_schema[key] == "B":
            #     last_evaluated_key[key] = bytes(last_evaluated_key[key])

        print(f"last_evaluated_key : {last_evaluated_key}")
        query_params["ExclusiveStartKey"] = last_evaluated_key

    if scan_condition:
        query_params["FilterExpression"] = scan_condition

    if index_name:
        query_params["IndexName"] = index_name

    if projection_exp:
        attr_names = dict()
        names = projection_exp.split(',')
        names = [n.strip() for n in names]
        for i in range(len(names)):
            attr_names['#' + str(i)] = names[i]
        query_params['ProjectionExpression'] = ', '.join(attr_names.keys())
        query_params['ExpressionAttributeNames'] = attr_names

    response = table.query(**query_params)
    items = response["Items"]
    last_evaluated_key = response.get("LastEvaluatedKey")

    while len(items) < limit and last_evaluated_key:
        query_params["ExclusiveStartKey"] = last_evaluated_key
        query_params["Limit"] = limit - len(items)
        response = table.query(**query_params)
        items.extend(response["Items"])
        last_evaluated_key = response.get("LastEvaluatedKey")

    return items, last_evaluated_key


def fetch_data_scan(table, last_evaluated_key=None):
    """dynamodb scan 데이터 페이징"""
    if last_evaluated_key:
        response = table.scan(Limit=50, ExclusiveStartKey=last_evaluated_key)
    else:
        response = table.scan(Limit=50)

    items = response["Items"]
    last_evaluated_key = response.get("LastEvaluatedKey")

    return items, last_evaluated_key


def put_item(table_name, item):
    table = get_resource_obj(table_name)
    table.put_item(Item=item)
    print(f"DynamoDB {table}.put_item : {item}")


def query_all_items(table, key_condition, scan_condition=None, index_forward=True):
    all_items = []
    last_evaluated_key = None

    while True:
        # Query 실행
        query_params = {
            "KeyConditionExpression": key_condition,
            "ScanIndexForward": index_forward,
        }

        if scan_condition:
            query_params["FilterExpression"] = scan_condition

        # 첫 페이지 이후에는 ExclusiveStartKey 추가
        if last_evaluated_key:
            query_params["ExclusiveStartKey"] = last_evaluated_key

        response = table.query(**query_params)

        # 결과 저장
        all_items.extend(response.get("Items", []))

        # 마지막 키가 없으면 종료
        last_evaluated_key = response.get("LastEvaluatedKey")
        if not last_evaluated_key:
            break

    return all_items


def switch_to_on_demand(table_name):
    try:
        response = dynamodb_client.update_table(
            TableName=table_name, BillingMode="PAY_PER_REQUEST"
        )
        print(f"Switch to on-demand (table : {table_name}, response : {response})")
        return response
    except botocore.exceptions.ClientError as e:
        error_code = e.response["Error"]["Code"]
        error_msg = e.response["Error"]["Message"]
        if error_code == "LimitExceededException":
            print(f"[WARNING] {error_code} : {error_msg}")
        else:
            traceback.print_exc()


def update_provisioned_capacity(table_name, write_capacity):
    response = dynamodb_client.update_table(
        TableName=table_name,
        ProvisionedThroughput={
            "ReadCapacityUnits": 1,
            "WriteCapacityUnits": write_capacity
        }
    )
    return response
