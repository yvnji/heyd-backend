import base64
import json
import os
import time_module
import zlib
from ast import literal_eval
from urllib import parse


def decode_data(data):
    """Decode data to dictionary

    :return
        e.g.
        {
            'messageType': 'DATA_MESSAGE',
            'owner': '412383802512',
            'logGroup': '/aws/lambda/pvat_datasource',
            'logStream': '2022/03/11/[1154]eb4322d760e74a65a22771bd3b663051',
            'subscriptionFilters': [
                'error-filter'
            ],
            'logEvents': [
                {
                    'id': '36728431823644122939830810202106245436852059342454325261',
                    'timestamp': 1646959843569,
                    'message': 'Traceback'
                }
            ]
        }
    """
    decoded_data = zlib.decompress(base64.b64decode(data), 16 + zlib.MAX_WBITS).decode(
        "utf-8"
    )
    print("decoded data : ", decoded_data)
    decoded_data = literal_eval(decoded_data)
    return decoded_data


def transform_data(decoded_data):
    """Get message string to send"""
    if len(decoded_data["logEvents"]) > 1:
        print("long logEvents")
    timestamp_sec = decoded_data["logEvents"][0]["timestamp"] / 1000
    where = decoded_data["logGroup"].strip("/").split("/")
    aws_service_name = where[1]
    service_object_name = where[-1]
    when_kor = time_module.fromtimestamp(timestamp_sec, time_module.tz_ko).strftime(
        "%Y-%m-%d %H:%M:%S.%f"
    )
    cause_msgs = decoded_data["logEvents"][0]["message"].strip().split("\r")[0]
    line = []
    line.append("ERROR from [%s]\n" % "/".join([aws_service_name, service_object_name]))
    line.append("AWS Region : %s" % os.environ["AWS_REGION"])
    line.append("AWS Service : %s" % aws_service_name)
    line.append("Service name : %s" % service_object_name)
    line.append("Timestamp : %s" % int(timestamp_sec))
    line.append("Korean time : %s" % when_kor)
    line.append("Log : %s" % cause_msgs)
    line.append(
        "Link : "
        + _cloudwatch_link(
            aws_service_name, service_object_name, int(timestamp_sec), cause_msgs
        )
    )
    print("msg : %s" % json.dumps(line))
    line_sum = "\n".join(line)
    return line_sum


def _cloudwatch_link(service_name, object_name, timestamp, match_str):
    """Get CloudWatch link found string matched"""
    time_from_millisec = timestamp * 1000
    time_to_millisec = (timestamp + 60) * 1000
    base = "https://{REGION}.console.aws.amazon.com/cloudwatch/home?region={REGION}#logsV2:log-groups/log-group/$252Faws$252F{SERVICE_NAME}$252F{OBJECT_NAME}/log-events$3Fstart$3D{TIME_FROM}$26end$3D{TIME_TO}$26filterPattern$3D$2522{MATCH_STR}$2522"
    return base.format(
        REGION=os.environ["AWS_REGION"],
        SERVICE_NAME=service_name,
        OBJECT_NAME=object_name,
        TIME_FROM=time_from_millisec,
        TIME_TO=time_to_millisec,
        MATCH_STR=parse.quote(match_str),
    )
