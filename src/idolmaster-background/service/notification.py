from thirdparty import firebase_admin


fcm = firebase_admin.FirebaseNotification()


def send_push_notification(fcm_token: str, title: str, body: str, data: dict = None) -> None:
    res = fcm.send_push_notification(fcm_token, title, body, data=data)
    print(f"send_push_notification res: {res}")
    if not res["success"]:
        raise Exception(res["error"])
