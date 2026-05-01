import json
import os

import const
from lib.decorator import mandatory_params
from lib.exception import IdolmasterBadRequestException
from lib.exception import IdolmasterResourceNotFoundExeption
from service import character as character_module
from service import mission as mission_module
from service import reaction as reaction_module
from thirdparty.mariadb import get_db_connection
from thirdparty import s3


@mandatory_params(["email", "game_id"])
def post_access_game(event, context, body):
    """미션게임 접속"""
    # 게임 id 체크
    if not mission_module.check_game(body["game_id"]):
        raise IdolmasterResourceNotFoundExeption(message="game_id not found")

    mission_module.access_game(body["game_id"], body["email"])


@mandatory_params(
    ["email", "game_id", "name", "background_file_path", "bgm_file_path", "character_ids", "language"]
)
def post_create_chatroom(event, context, body):
    """미션게임 채팅방 생성"""
    character_ids = body["character_ids"].replace(" ", "").split(",")
    cursor = get_db_connection().cursor()

    # 게임 id 체크
    if not mission_module.check_game(body["game_id"], cursor=cursor):
        raise IdolmasterResourceNotFoundExeption(message="game_id not found")

    # 캐릭터 체크
    for cid in character_ids:
        character_item = character_module.get_character(cid, cursor=cursor)
        if not character_item:
            raise IdolmasterResourceNotFoundExeption(message=f"Character ID not found ({cid})")
        elif not character_item["type"] == const.CHARACTER_TYPE_MISSION:
            raise IdolmasterBadRequestException(message="Invalid type")

    mission_module.create_chatroom_meta(
        body["email"],
        body["game_id"],
        body["name"],
        body["background_file_path"].strip('/'),
        body.get("bgm_file_path", "").strip('/'),
        character_ids,
        body["language"],
    )


@mandatory_params(["email", "comment", "game_id"])
def post_create_comment(event, context, body):
    """미션게임 댓글 등록"""
    # 게임 id 체크
    if not mission_module.check_game(body["game_id"]):
        raise IdolmasterResourceNotFoundExeption(message="game_id not found")

    target_id = reaction_module.get_reaction_id(game_id=int(body["game_id"]))
    comment_id = reaction_module.create_comment(
        body["email"], target_id, body["comment"]
    )
    return {"data": {"comment_id": comment_id}}


@mandatory_params(
    [
        "email",
        "title",
        "introduce",
        "thumbnail_file",
        "overview",
        "mission_info",
        "qa",
        "ending_story",
        "true_ending_image_file_path",
        "normal_ending_image_file_path",
        "bad_ending_image_file_path",
    ]
)
def post_create_game(event, context, body):
    """미션게임 생성"""
    true_file_path = body["true_ending_image_file_path"].strip("/")
    normal_file_path = body["normal_ending_image_file_path"].strip("/")
    bad_file_path = body["bad_ending_image_file_path"].strip("/")

    # json 포맷 맞는지 확인
    try:
        qa_list = json.loads(body["qa"])
        ending_story = json.loads(body["ending_story"])
    except json.decoder.JSONDecodeError:
        raise IdolmasterBadRequestException(message="Invalid JSON format")

    # 엔딩 이미지 파일 S3에 존재하는지 확인
    bucket_name = const.S3_BUCKET_NAME[os.environ["AWS_REGION"]][
        os.environ["API_ALIAS"]
    ]
    s3.check_object(bucket_name, true_file_path)
    s3.check_object(bucket_name, normal_file_path)
    s3.check_object(bucket_name, bad_file_path)

    ending_list = [
        {
            "type": "true",
            "image_file_path": true_file_path,
            "story": ending_story["true_story"],
        },
        {
            "type": "normal",
            "image_file_path": normal_file_path,
            "story": ending_story["normal_story"],
        },
        {
            "type": "bad",
            "image_file_path": bad_file_path,
            "story": ending_story["bad_story"],
        },
    ]
    game_id = mission_module.create_game(
        body["email"],
        body["title"],
        body["introduce"],
        body["thumbnail_file"],
        body["overview"],
        body["mission_info"],
        qa_list,
        ending_list,
    )
    return {"data": {"game_id": game_id}}


@mandatory_params(["comment_id"])
def post_delete_comment(event, context, body):
    """미션게임 댓글 삭제"""
    comment = reaction_module.get_comment(body["comment_id"])

    # comment_id 확인
    if not comment:
        raise IdolmasterResourceNotFoundExeption(message="comment_id not found")

    # TODO 사용자의 comment 권한 확인 (인증 적용 이후)

    reaction_module.delete_comment(body["comment_id"])


@mandatory_params(["email", "emoji_id", "game_id"])
def post_delete_emoji(event, context, body):
    """미션게임 이모지 취소"""
    cursor = get_db_connection().cursor()

    # game_id 확인
    if not mission_module.check_game(body["game_id"], cursor=cursor):
        raise IdolmasterResourceNotFoundExeption(message="game_id not found")

    # emoji_id 확인
    emoji_list = reaction_module.list_emoji(cursor=cursor)
    if body["emoji_id"] not in [e["emoji_id"] for e in emoji_list]:
        raise IdolmasterResourceNotFoundExeption(message="emoji_id not found")

    target_id = reaction_module.get_reaction_id(game_id=int(body["game_id"]))
    reaction_module.cancel_emoji(target_id, body["email"], body["emoji_id"])


@mandatory_params(["email", "game_id"])
def post_exit_game(event, context, body):
    """미션게임 나가기"""
    # game_id 확인
    if not mission_module.check_game(body["game_id"]):
        raise IdolmasterResourceNotFoundExeption(message="game_id not found")

    rooms = mission_module.list_chatroom(body["game_id"], body["email"])
    for room in rooms:
        mission_module.remove_chatroom(room["game_chat_id"])


@mandatory_params(["game_chat_id"])
def post_get_chatroom_info(event, context, body):
    """미션게임 채팅방 정보 조회"""
    # game_chat_id 확인
    if not mission_module.get_chatroom(body["game_chat_id"]):
        raise IdolmasterResourceNotFoundExeption(message="game_chat_id not found")

    # TODO 사용자의 채팅방 권한 확인 (인증 적용 이후)

    return {"data": mission_module.get_chatroom_info(body["game_chat_id"])}


@mandatory_params(["email", "game_id"])
def post_get_detail(event, context, body):
    """미션게임 상세 조회"""
    game_id = body["game_id"]
    email = body["email"]
    cursor = get_db_connection().cursor()

    # game_id 확인
    if not mission_module.check_game(game_id, cursor=cursor):
        raise IdolmasterResourceNotFoundExeption(message="game_id not found")

    game_item = mission_module.get_game(game_id, email, cursor=cursor)
    game_item["chatrooms"] = mission_module.list_chatroom(game_id, email, cursor=cursor)

    return {"data": game_item}


@mandatory_params(["email", "game_id"])
def post_get_game(event, context, body):
    """미션게임 정보 조회"""
    game_id = body["game_id"]
    email = body["email"]

    # game_id 확인
    if not mission_module.check_game(body["game_id"]):
        raise IdolmasterResourceNotFoundExeption(message="game_id not found")

    return {"data": mission_module.get_game(game_id, email)}


@mandatory_params(["email", "comment_id"])
def post_like_comment(event, context, body):
    """미션게임 댓글 추천 등록"""
    comment = reaction_module.get_comment(body["comment_id"])

    # comment_id 확인
    if not comment:
        raise IdolmasterResourceNotFoundExeption(message="comment_id not found")

    target_id = reaction_module.get_reaction_id(comment_id=int(body["comment_id"]))
    reaction_module.submit_like(target_id, body["email"])


@mandatory_params(["email", "game_id"])
def post_like_game(event, context, body):
    """미션게임 추천 등록"""
    # game_id 확인
    if not mission_module.check_game(body["game_id"]):
        raise IdolmasterResourceNotFoundExeption(message="game_id not found")

    target_id = reaction_module.get_reaction_id(game_id=int(body["game_id"]))
    reaction_module.submit_like(target_id, body["email"])


def post_list_chatroom_background(event, context, body):
    """미션게임 채팅방 적용 가능한 배경이미지 파일 경로 리스트 조회"""
    path_list = mission_module.list_chatroom_background()
    return {"data": path_list}


def post_list_chatroom_bgm(event, context, body):
    """미션게임 채팅방 적용 가능한 bgm 파일 경로 리스트 조회"""
    path_list = mission_module.list_chatroom_bgm()
    return {"data": path_list}


@mandatory_params(["email", "game_id"])
def post_list_chatroom(event, context, body):
    """해당 미션게임 채팅방 리스트 조회"""
    # game_id 확인
    if not mission_module.check_game(body["game_id"]):
        raise IdolmasterResourceNotFoundExeption(message="game_id not found")

    chat_list = mission_module.list_chatroom(body["game_id"], body["email"])
    return {"data": chat_list}


@mandatory_params(["email", "game_id"])
def post_list_comments(event, context, body):
    """미션게임 댓글 리스트 조회"""
    params = event["queryStringParameters"]
    params = params if params else {}
    sort_by = params.get("sort_by", "newest")  # "newest", "top"
    page = int(params.get("page", 1))
    page_size = int(params.get("page_size", 10))
    offset = (page - 1) * page_size

    # game_id 확인
    if not mission_module.check_game(body["game_id"]):
        raise IdolmasterResourceNotFoundExeption(message="game_id not found")

    # sort_by 확인
    if sort_by not in ["top", "newest"]:
        raise IdolmasterBadRequestException(message="Invalid sort_by")

    target_id = reaction_module.get_reaction_id(game_id=body["game_id"])
    comments = reaction_module.list_comments(
        target_id, body["email"], sort_by=sort_by, page_size=page_size, offset=offset
    )
    return {
        "data": comments,
        "total": len(reaction_module.get_total_comments(target_id)),
    }


@mandatory_params(["email"])
def post_list_games(event, context, body):
    """홈화면에서 미션게임 리스트 조회"""
    params = event["queryStringParameters"]
    params = params if params else {}
    page = int(params.get("page", 1))
    page_size = int(params.get("page_size", 10))
    offset = (page - 1) * page_size
    games = mission_module.list_games(body["email"], page_size, offset)
    return {"data": games}


@mandatory_params(["game_chat_id"])
def post_list_previous_chat(event, context, body):
    """미션게임 채팅방 이전 채팅 리스트 조회"""
    # game_chat_id 확인
    if not mission_module.get_chatroom(body["game_chat_id"]):
        raise IdolmasterResourceNotFoundExeption(message="game_chat_id not found")

    # TODO 사용자의 채팅방 권한 확인 (인증 적용 이후)

    previous_chat_list = mission_module.list_previous_chat(
        body["game_chat_id"], body.get("last_evaluated_key")
    )
    return {
        "data": previous_chat_list["chats"],
        "last_evaluated_key": previous_chat_list["last_evaluated_key"],
    }


@mandatory_params(["game_id"])
def post_list_questions(event, context, body):
    """미션게임 미션 질문 리스트 조회"""
    # game_id 확인
    if not mission_module.check_game(body["game_id"]):
        raise IdolmasterResourceNotFoundExeption(message="game_id not found")

    return {"data": mission_module.list_questions(body["game_id"])}


@mandatory_params(["email", "emoji_id", "game_id"])
def post_post_emoji(event, context, body):
    """미션게임 이모지 등록"""
    # game_id 확인
    if not mission_module.check_game(body["game_id"]):
        raise IdolmasterResourceNotFoundExeption(message="game_id not found")

    # emoji_id 확인
    emoji_list = reaction_module.list_emoji()
    if body["emoji_id"] not in [e["emoji_id"] for e in emoji_list]:
        raise IdolmasterResourceNotFoundExeption(message="emoji_id not found")

    target_id = reaction_module.get_reaction_id(game_id=int(body["game_id"]))
    reaction_module.submit_emoji(target_id, body["email"], body["emoji_id"])


@mandatory_params(
    [
        "game_id",
        "question_id_1",
        "question_id_2",
        "question_id_3",
        "answer_q1",
        "answer_q2",
        "answer_q3",
    ]
)
def post_submit_mission(event, context, body):
    """미션게임 미션 질문 제출 및 결과 조회"""
    # game_id 확인
    if not mission_module.check_game(body["game_id"]):
        raise IdolmasterResourceNotFoundExeption(message="game_id not found")

    # 질문 id 확인
    questions = mission_module.list_questions(body["game_id"])
    question_ids = sorted([q["question_id"] for q in questions])
    question_ids_body = sorted(
        [body["question_id_1"], body["question_id_2"], body["question_id_3"]]
    )
    if not question_ids == question_ids_body:
        raise IdolmasterResourceNotFoundExeption(
            message="Question ID not found in this game"
        )

    ending = mission_module.submit_mission(
        body["game_id"],
        [
            {"question_id": body["question_id_1"], "answer": body["answer_q1"]},
            {"question_id": body["question_id_2"], "answer": body["answer_q2"]},
            {"question_id": body["question_id_3"], "answer": body["answer_q3"]},
        ],
    )
    return {"data": ending}


@mandatory_params(["comment_id", "email"])
def post_unlike_comment(event, context, body):
    """미션게임 댓글 추천 취소"""
    comment = reaction_module.get_comment(body["comment_id"])

    # comment_id 확인
    if not comment:
        raise IdolmasterResourceNotFoundExeption(message="comment_id not found")

    target_id = reaction_module.get_reaction_id(comment_id=int(body["comment_id"]))
    reaction_module.cancel_like(target_id, body["email"])


@mandatory_params(["game_id", "email"])
def post_unlike_game(event, context, body):
    """미션게임 추천 취소"""
    # game_id 확인
    if not mission_module.check_game(body["game_id"]):
        raise IdolmasterResourceNotFoundExeption(message="game_id not found")

    target_id = reaction_module.get_reaction_id(game_id=int(body["game_id"]))
    reaction_module.cancel_like(target_id, body["email"])


@mandatory_params(["comment_id", "comment"])
def post_update_comment(event, context, body):
    """미션게임 댓글 수정"""
    comment = reaction_module.get_comment(body["comment_id"])

    # comment_id 확인
    if not comment:
        raise IdolmasterResourceNotFoundExeption(message="comment_id not found")

    # TODO 사용자의 comment 권한 확인 (인증 적용 이후)

    reaction_module.update_comment(body["comment_id"], body["comment"])


@mandatory_params(["image_file"])
def post_upload_chatroom_background(event, context, body):
    """미션게임 채팅방 배경화면 등록"""
    file_name = mission_module.upload_chatroom_background(body["image_file"])
    return {"data": {"image_file_path": file_name}}


@mandatory_params(["image_file"])
def post_upload_ending_background(event, context, body):
    """미션게임 엔딩 배경화면 등록"""
    file_name = mission_module.upload_ending_background(body["image_file"])
    return {"data": {"image_file_path": file_name}}
