import json

from service import websocket


def chat_join(event, context, body):
    """웹소켓 연결 시, 채팅방에 참여하는 사용자를 등록합니다."""
    websocket.join_chat(
        event["requestContext"]["connectionId"], body["email"], body["chatroom_id"]
    )
    return {}


def game_chat_join(event, context, body):
    """게임채팅방 참여하는 사용자 등록"""
    websocket.join_game_chat(
        event["requestContext"]["connectionId"], body["email"], body["game_chat_id"]
    )
    return {}


def game_chat_send_message(event, context, body):
    """게임채팅방 메세지 전송"""
    # 사용자 메세지 전송
    res = websocket.send_message_game_chat(
        event["requestContext"]["connectionId"],
        event["requestContext"]["domainName"],
        body["email"],
        body["game_chat_id"],
        body["message"],
        body["character_id"],
        body.get("chat_id")
    )

    # AI 응답 전송
    # 사용자 메세지 전송 성공했을 경우만
    if res:
        websocket.send_message_game_chat_ai(
            event["requestContext"]["domainName"],
            body["game_chat_id"],
            body["character_id"],
            body.get("safe_chat", False),
        )
    return {}


def groupchat_join(event, context, body):
    """웹소켓 연결 시, 채팅방에 참여하는 사용자를 등록합니다."""
    websocket.join_groupchat(
        event["requestContext"]["connectionId"], body["email"], body["groupchat_id"]
    )
    return {}


def groupsend_message(event, context, body):
    """메세지 전달하기"""
    # 사용자 메세지 전송
    res = websocket.send_message_groupchat(
        event["requestContext"]["connectionId"],
        event["requestContext"]["domainName"],
        body["email"],
        body["groupchat_id"],
        body["message"],
        body["chat_id"],
        body["chat_save"],
        body["character_uuid"],
    )

    # user만 멘션되었을 때 AI 대답 안하도록
    # 사용자 메세지 전송 성공했을 경우만
    if res:
        if body["user_mentioned"] is False:
            # AI 응답 전송
            websocket.send_message_groupchat_ai(
                event["requestContext"]["domainName"],
                body["email"],
                body["groupchat_id"],
                body.get("character_uuid"),
                body.get("safe_chat", False),
            )
    return {}


def ping(event, context, body):
    return {"statusCode": 200, "body": json.dumps("Ping")}


def send_message(event, context, body):
    """메세지 전달하기"""
    # 사용자 메세지 전송
    res = websocket.send_message_chat(
        event["requestContext"]["connectionId"],
        event["requestContext"]["domainName"],
        body["email"],
        body["chatroom_id"],
        body["message"],
        body["chat_id"],
    )

    # AI 응답 전송
    # 사용자 메세지 전송 성공했을 경우만
    if res:
        websocket.send_message_chat_ai(
            event["requestContext"]["domainName"],
            event["requestContext"]["connectionId"],
            body["chatroom_id"],
            body.get("character_type", ""),
            body.get("safe_chat", False),
        )

    return {}
