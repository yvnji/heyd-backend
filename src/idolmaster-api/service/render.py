import os
from urllib import request
import json

import const
from lib.client import s3_client


def ready(
    avatar_id: str, event_name: str, status: str, render_url: str, export_url: str
):
    returncode = 0

    if event_name == "render.ready" and status == "ready":
        avatar_image_file = request.urlopen(render_url).read()
        filename = f"avaturn_character/{avatar_id}.jpg"
        s3_client.put_object(
            Bucket=const.S3_BUCKET_NAME[os.environ["AWS_REGION"]][
                os.environ["API_ALIAS"]
            ],
            Key=filename,
            Body=avatar_image_file,
        )
    # elif event_name == 'avatar.ready' and status == 'ready':
    #     data = {}
    #     try:
    #         avatar_url = os.environ["createExport"].replace('{avatar_id}',avatar_id)
    #         response = http.request('POST', avatar_url, headers=headers)
    #         print(response.status)
    #         if response.status == 200:
    #             data = json.loads(response.data.decode('utf-8'))
    #             print(data['status'])

    #     except Exception as e:
    #         logger.error(" ====== ‼️ avatar_render_ready ERROR: {} ======".format(traceback.format_exc()))
    #         returncode = 0

    elif event_name == "export.ready" and status == "ready":
        avatar_file = request.urlopen(export_url).read()
        # 경로 수정 avaturn_character/{}.glb
        filename = f"avaturn_character/{avatar_id}.glb"
        s3_client.put_object(
            Bucket=const.S3_BUCKET_NAME[os.environ["AWS_REGION"]][
                os.environ["API_ALIAS"]
            ],
            Key=filename,
            Body=avatar_file,
        )

        # EC2 서버로 압축 요청
        compress_api_url = (
            const.URL_RETARGETING[os.environ["AWS_REGION"]]
            + const.COMPRESS_AND_SAVE_API
        )
        payload = json.dumps(
            {
                "avatar_file_path": filename,
                "env_name": os.environ["API_ALIAS"],
                "BUCKET_NAME": const.S3_BUCKET_NAME[os.environ["AWS_REGION"]][
                    os.environ["API_ALIAS"]
                ],
            }
        ).encode("utf-8")

        req = request.Request(
            compress_api_url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with request.urlopen(req) as response:
                status_code = response.getcode()
                body = response.read().decode("utf-8")
                print(f"✅ 압축 요청 성공 status: {status_code}")
                print(f"✅ 응답 내용: {body}")
        except Exception as e:
            print("❌ EC2 압축 요청 중 오류 발생:", e)

        # # 압축된 파일 S3에 저장
        # filename = f"avaturn_character/{avatar_id}.glb"
        # s3_client.put_object(
        #     Bucket=const.S3_BUCKET_NAME[os.environ["AWS_REGION"]][
        #         os.environ["API_ALIAS"]
        #     ],
        #     Key=filename,
        #     Body=compressed_data,
        # )

    return {"result": returncode}
