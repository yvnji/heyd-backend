import json
from threading import Lock

import boto3
from firebase_admin import messaging, credentials, initialize_app


class SingletonMeta(type):
    _instances = {}
    _lock = Lock()

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            with cls._lock:
                if cls not in cls._instances:
                    cls._instances[cls] = super().__call__(*args, **kwargs)
        return cls._instances[cls]


class FirebaseNotification(metaclass=SingletonMeta):
    def __init__(self):
        if not hasattr(self, '_initialized'):
            self._initialized = True
            self._initialize_firebase()

    def _initialize_firebase(self):
        """Firebase Admin SDK 초기화"""
        try:
            key_file = json.loads(self._get_key_file())
            cred = credentials.Certificate(key_file)
            initialize_app(cred)
        except Exception as e:
            self._initialized = False
            raise Exception(f"Firebase initialization failed: {str(e)}")

    def _get_key_file(self) -> str:
        """파라미터 스토어에 저장되어 있는 키 파일 조회"""
        try:
            PARAMETER_NAME = "/KEY_FILE/firebase_key_file"
            ssm = boto3.client("ssm")
            res = ssm.get_parameter(
                Name=PARAMETER_NAME,
                WithDecryption=True
            )
            return res["Parameter"]["Value"]
        except Exception as e:
            raise Exception(f"Failed to get key file from Parameter Store: {str(e)}")

    def send_push_notification(
        self,
        token: str,
        title: str,
        body: str,
        data: dict = None
    ) -> dict:
        """
        단일 사용자에게 푸시 알림을 보냅니다.

        Args:
            token (str): 사용자의 FCM 토큰
            title (str): 알림 제목
            body (str): 알림 내용
            data (dict, optional): 추가 데이터. key-value 형태의 커스텀 데이터. Defaults to None.

        Returns:
            dict: 전송 결과
                {
                    "success": bool,   # 전송 성공 여부
                    "message_id": str,   # 성공 시 메시지 ID
                    "error": str   # 실패 시 에러 메시지
                }
        """
        try:
            # 알림 메시지 구성
            message = messaging.Message(
                notification=messaging.Notification(
                    title=title,
                    body=body
                ),
                data=data if data else {},
                token=token,
                # # Android 특정 설정
                # android=messaging.AndroidConfig(
                #     priority='high',
                #     notification=messaging.AndroidNotification(
                #         icon='notification_icon',
                #         color='#4CAF50',
                #         sound='default'
                #     )
                # ),
                # # iOS 특정 설정
                # apns=messaging.APNSConfig(
                #     headers={
                #         'apns-priority': '10'
                #     },
                #     payload=messaging.APNSPayload(
                #         aps=messaging.Aps(
                #             sound='default',
                #             badge=1
                #         )
                #     )
                # )
            )

            # 메시지 전송
            response = messaging.send(message)
            return {
                "success": True,
                "message_id": response
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def send_multicast_notification(
        self,
        tokens: list,
        title: str,
        body: str,
        data: dict = None
    ) -> dict:
        """
        여러 사용자에게 동시에 푸시 알림을 보냅니다.

        Args:
            tokens (list): FCM 토큰 리스트
            title (str): 알림 제목
            body (str): 알림 내용
            data (dict, optional): 추가 데이터. key-value 형태의 커스텀 데이터. Defaults to None.

        Returns:
            dict: 전송 결과
                {
                    "success": bool,  # 전체 전송 프로세스 성공 여부
                    "success_count": int,  # 성공적으로 전송된 메시지 수
                    "failure_count": int,  # 전송 실패한 메시지 수
                    "responses": list[dict]  # 각 토큰별 전송 결과
                        [
                            {
                                "success": bool,  # 해당 토큰 전송 성공 여부
                                "message_id": str,  # 성공 시 메시지 ID
                                "error": str  # 실패 시 에러 메시지
                            },
                            ...
                        ]
                }
        """
        try:
            # 멀티캐스트 메시지 구성
            message = messaging.MulticastMessage(
                notification=messaging.Notification(
                    title=title,
                    body=body
                ),
                data=data if data else {},
                tokens=tokens,
                # android=messaging.AndroidConfig(
                #     priority='high',
                #     notification=messaging.AndroidNotification(
                #         # icon='notification_icon',
                #         # color='#4CAF50',
                #         # sound='default'
                #     )
                # ),
                # apns=messaging.APNSConfig(
                #     headers={
                #         'apns-priority': '10'
                #     },
                #     payload=messaging.APNSPayload(
                #         aps=messaging.Aps(
                #             # sound='default',
                #             # badge=1
                #         )
                #     )
                # )
            )

            # 멀티캐스트 전송
            response = messaging.send_multicast(message)

            return {
                "success": True,
                "success_count": response.success_count,
                "failure_count": response.failure_count,
                "responses": [
                    {"success": resp.success, "message_id": resp.message_id, "error": str(resp.exception) if resp.exception else None}
                    for resp in response.responses
                ]
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
