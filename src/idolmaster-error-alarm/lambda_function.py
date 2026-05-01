import webhook
import ETL


def lambda_handler(event, context):
    """Handler receive logs from AWS CloudWatch.
    Only error logs are handled.

    :param event
        {
            'awslogs': {
                'data': '{Base64-encoded .gzip file archive}'
            }
        }
    """
    print(event)

    data = event["awslogs"]["data"]
    decoded_data = ETL.decode_data(data)
    msg = ETL.transform_data(decoded_data)
    webhook.to_slack(msg)
