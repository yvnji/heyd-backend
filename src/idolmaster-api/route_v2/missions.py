import json
import os

import const
from lib.decorator import mandatory_params
from lib.exception import IdolmasterBadRequestException
from lib.exception import IdolmasterForbiddenException
from lib.exception import IdolmasterResourceNotFoundExeption
from service import character as character_module
from service import mission as mission_module
from service import reaction as reaction_module
from thirdparty.mariadb import get_db_connection
from thirdparty import s3


@mandatory_params(["missions", "comments"])
def delete_missions_comments(event, context, params):
    """미션게임 댓글 삭제
    post_delete_comment 수정
    parameter missions(mission_id) 추가
    exception 404 추가 (game_id)
    """
    email = event["requestContext"]["authorizer"]["email"]
    game_id = params["missions"]
    comment_id = params["comments"]

    # game_id 확인
    if not mission_module.check_game(game_id):
        raise IdolmasterResourceNotFoundExeption(message="game_id not found")
    game_id = int(game_id)

    # comment_id 확인
    comment = reaction_module.get_comment(comment_id)
    if not comment:
        raise IdolmasterResourceNotFoundExeption(
            message="comment_id not found",
            result_code=1)
    comment_id = int(comment_id)

    # check comment in game_id
    reaction_id_game = reaction_module.get_reaction_id(game_id=game_id)
    if comment["target_id"] != reaction_id_game:
        raise IdolmasterBadRequestException(
            message="Invalid game_id and comment_id",
            result_code=1)

    # 사용자의 comment 권한 확인
    if comment["email"] != email:
        raise IdolmasterForbiddenException(message="Forbidden")

    reaction_module.delete_comment(comment_id)


@mandatory_params(["missions", "comments"])
def delete_missions_comments_likes(event, context, params):
    """미션게임 댓글 추천 취소
    post_unlike_comment 수정
    parameter missions(mission_id) 추가
    exception 404 추가 (game_id)
    """
    email = event["requestContext"]["authorizer"]["email"]
    game_id = params["missions"]
    comment_id = params["comments"]

    # game_id 확인
    if not mission_module.check_game(game_id):
        raise IdolmasterResourceNotFoundExeption(message="game_id not found")
    game_id = int(game_id)

    # comment_id 확인
    comment = reaction_module.get_comment(comment_id)
    if not comment:
        raise IdolmasterResourceNotFoundExeption(
            message="comment_id not found",
            result_code=1)
    comment_id = int(comment_id)

    # check comment in game_id
    reaction_id_game = reaction_module.get_reaction_id(game_id=game_id)
    if comment["target_id"] != reaction_id_game:
        raise IdolmasterBadRequestException(message="Invalid game_id and comment_id")

    target_id = reaction_module.get_reaction_id(comment_id=comment_id)
    reaction_module.cancel_like(target_id, email)


@mandatory_params(["missions"])
def delete_missions_connections(event, context, params):
    """미션게임 나가기
    post_exit_game 수정
    """
    email = event["requestContext"]["authorizer"]["email"]
    game_id = params["missions"]

    # game_id 확인
    if not mission_module.check_game(game_id):
        raise IdolmasterResourceNotFoundExeption(message="game_id not found")
    game_id = int(game_id)

    rooms = mission_module.list_chatroom(game_id, email)
    for room in rooms:
        mission_module.remove_chatroom(room["game_chat_id"])


@mandatory_params(["missions", "emojis"])
def delete_missions_emojis(event, context, params):
    """미션게임 이모지 취소
    post_delete_emoji 수정
    """
    email = event["requestContext"]["authorizer"]["email"]
    game_id = params["missions"]
    emoji_id = params["emojis"]
    cursor = get_db_connection().cursor()

    # game_id 확인
    if not mission_module.check_game(game_id, cursor=cursor):
        raise IdolmasterResourceNotFoundExeption(message="game_id not found")
    game_id = int(game_id)

    # emoji_id 확인
    emoji_list = reaction_module.list_emoji(cursor=cursor)
    if emoji_id not in [str(e["emoji_id"]) for e in emoji_list]:
        raise IdolmasterResourceNotFoundExeption(
            message="emoji_id not found",
            result_code=1)
    emoji_id = int(emoji_id)

    target_id = reaction_module.get_reaction_id(game_id=int(game_id))
    reaction_module.cancel_emoji(target_id, email, emoji_id)


@mandatory_params(["missions"])
def delete_missions_likes(event, context, params):
    """미션게임 추천 취소
    post_unlike_game 수정
    """
    email = event["requestContext"]["authorizer"]["email"]
    game_id = params["missions"]

    # game_id 확인
    if not mission_module.check_game(game_id):
        raise IdolmasterResourceNotFoundExeption(message="game_id not found")
    game_id = int(game_id)

    target_id = reaction_module.get_reaction_id(game_id=int(game_id))
    reaction_module.cancel_like(target_id, email)


def get_missions(event, context, params):
    """미션게임 단일, 복수 조회
    post_list_games, post_get_game 통합
    """
    email = event["requestContext"]["authorizer"]["email"]
    game_id = params.get("missions")
    cursor = get_db_connection().cursor()
    ret = None

    # 단일 조회
    if game_id:
        # game_id 확인
        if not mission_module.check_game(game_id):
            raise IdolmasterResourceNotFoundExeption(message="game_id not found")
        game_id = int(game_id)
        game_item = mission_module.get_game(game_id, email, cursor=cursor)

        ret = {"data": game_item}

    # 복수 조회
    else:
        # check type
        try:
            page = int(params.get("page", 1))
            page_size = int(params.get("page_size", 10))
            if page < 1 or page_size < 1:
                raise ValueError
        except ValueError:
            raise IdolmasterBadRequestException(
                message="Invalid params",
                result_code=1)

        offset = (page - 1) * page_size
        games = mission_module.list_games(email, page_size, offset)
        ret = {"data": games}

    return ret


@mandatory_params(["missions"])
def get_missions_chatrooms(event, context, params):
    """미션게임 단일, 복수 채팅방 정보 조회
    post_list_chatroom, post_get_chatroom_info 통합
    """
    email = event["requestContext"]["authorizer"]["email"]
    game_id = params["missions"]
    game_chat_id = params.get("chatrooms")
    ret = None

    # game_id 확인
    if not mission_module.check_game(game_id):
        raise IdolmasterResourceNotFoundExeption(message="game_id not found")
    game_id = int(game_id)

    # 단일 조회
    if game_chat_id:
        # game_chat_id 확인
        game_chatroom = mission_module.get_chatroom(game_chat_id)
        if not game_chatroom:
            raise IdolmasterResourceNotFoundExeption(
                message="game_chat_id not found",
                result_code=1)
        game_chat_id = int(game_chat_id)

        # game_id, game_chat_id 관계 확인
        if game_id != game_chatroom["game_id"]:
            raise IdolmasterBadRequestException(
                message="Invalid game_id and game_chat_id",
                result_code=1)

        # 사용자의 채팅방 권한 확인
        if game_chatroom["email"] != email:
            raise IdolmasterForbiddenException

        ret = {"data": mission_module.get_chatroom_info(game_chat_id)}

    # 복수 조회
    else:
        ret = {"data": mission_module.list_chatroom(game_id, email)}

    return ret


@mandatory_params(["missions", "chatrooms"])
def get_missions_chatrooms_chats(event, context, params):
    """미션게임 채팅방 이전 채팅 리스트 조회
    post_list_previous_chat 수정
    parameter missions(mission_id) 추가
    exception 404 추가 (game_id)
    """
    email = event["requestContext"]["authorizer"]["email"]
    game_id = params["missions"]
    game_chat_id = params["chatrooms"]
    last_evaluated_key = params.get("last_evaluated_key")

    # game_id 확인
    if not mission_module.check_game(game_id):
        raise IdolmasterResourceNotFoundExeption(message="game_id not found")
    game_id = int(game_id)

    # game_chat_id 확인
    game_chatroom = mission_module.get_chatroom(game_chat_id)
    if not game_chatroom:
        raise IdolmasterResourceNotFoundExeption(
            message="game_chat_id not found",
            result_code=1)
    game_chat_id = int(game_chat_id)

    # game_id, game_chat_id 관계 확인
    if game_id != game_chatroom["game_id"]:
        raise IdolmasterBadRequestException(
            message="Invalid game_id and game_chat_id",
            result_code=1)

    # 사용자의 채팅방 권한 확인
    if game_chatroom["email"] != email:
        raise IdolmasterForbiddenException

    previous_chat_list = mission_module.list_previous_chat(
        game_chat_id, last_evaluated_key
    )
    return {
        "data": previous_chat_list["chats"],
        "last_evaluated_key": previous_chat_list["last_evaluated_key"],
    }


@mandatory_params(["missions"])
def get_missions_comments(event, context, params):
    """미션게임 댓글 리스트 조회
    post_list_comments 수정
    """
    email = event["requestContext"]["authorizer"]["email"]
    game_id = params["missions"]
    sort_by = params.get("sort_by", "newest")  # "newest", "top"

    # check type
    try:
        page = int(params.get("page", 1))
        page_size = int(params.get("page_size", 10))
        offset = (page - 1) * page_size
        if sort_by not in ("top", "newest"):
            raise ValueError
    except ValueError:
        raise IdolmasterBadRequestException(
            message="Invalid params",
            result_code=1)

    # game_id 확인
    if not mission_module.check_game(game_id):
        raise IdolmasterResourceNotFoundExeption(message="game_id not found")
    game_id = int(game_id)

    target_id = reaction_module.get_reaction_id(game_id=game_id)
    comments = reaction_module.list_comments(
        target_id, email, sort_by=sort_by, page_size=page_size, offset=offset
    )
    return {
        "data": comments,
        "total": len(reaction_module.get_total_comments(target_id)),
    }


@mandatory_params(["missions"])
def get_missions_questions(event, context, params):
    """미션게임 미션 질문 리스트 조회
    post_list_questions 수정
    """
    game_id = params["missions"]

    # game_id 확인
    if not mission_module.check_game(game_id):
        raise IdolmasterResourceNotFoundExeption(message="game_id not found")
    game_id = int(game_id)

    return {"data": mission_module.list_questions(game_id)}


@mandatory_params(
    [
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
def post_missions(event, context, body):
    """미션게임 생성
    post_create_game 수정
    """
    email = event["requestContext"]["authorizer"]["email"]
    title = body["title"]
    intro = body["introduce"]
    thumbnail_file = body["thumbnail_file"]
    overview = body["overview"]
    info = body["mission_info"]
    true_file_path = body["true_ending_image_file_path"].strip("/")
    normal_file_path = body["normal_ending_image_file_path"].strip("/")
    bad_file_path = body["bad_ending_image_file_path"].strip("/")

    # json 포맷 맞는지 확인
    try:
        qa_list = json.loads(body["qa"])
        ending_story = json.loads(body["ending_story"])
    except json.decoder.JSONDecodeError:
        raise IdolmasterBadRequestException(
            message="Invalid params",
            result_code=1)

    # 엔딩 이미지 파일 S3에 존재하는지 확인
    # 가독성을 위해 raise 발생
    bucket_name = const.S3_BUCKET_NAME[os.environ["AWS_REGION"]][
        os.environ["API_ALIAS"]
    ]
    try:
        s3.check_object(bucket_name, true_file_path)
        s3.check_object(bucket_name, normal_file_path)
        s3.check_object(bucket_name, bad_file_path)
    except IdolmasterResourceNotFoundExeption:
        raise IdolmasterResourceNotFoundExeption

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
        email,
        title,
        intro,
        thumbnail_file,
        overview,
        info,
        qa_list,
        ending_list,
    )
    return {"data": {"game_id": game_id}}


@mandatory_params(
    ["missions", "name", "background_file_path", "bgm_file_path", "character_ids", "language"]
)
def post_missions_chatrooms(event, context, body):
    """미션게임 채팅방 생성
    post_create_chatroom 수정
    """
    email = event["requestContext"]["authorizer"]["email"]
    game_id = body["missions"]
    name = body["name"]
    background_path = body["background_file_path"].strip('/')
    bgm_path = body.get("bgm_file_path", "").strip('/')
    character_ids = body["character_ids"].replace(" ", "").split(",")
    language = body["language"]
    cursor = get_db_connection().cursor()

    # 게임 id 체크
    if not mission_module.check_game(game_id, cursor=cursor):
        raise IdolmasterResourceNotFoundExeption(message="game_id not found")
    game_id = int(game_id)

    # 캐릭터 체크
    if len(character_ids) > 2:
        raise IdolmasterBadRequestException(
            message="Too many character_id",
            result_code=1)
    for cid in character_ids:
        character_item = character_module.get_character(cid, cursor=cursor)
        if not character_item:
            raise IdolmasterResourceNotFoundExeption(
                message="character_ids not found",
                result_code=1)
        elif not character_item["type"] == const.CHARACTER_TYPE_MISSION:
            raise IdolmasterBadRequestException(
                message="Invalid character type",
                result_code=2)

    mission_module.create_chatroom_meta(
        email,
        game_id,
        name,
        background_path,
        bgm_path,
        character_ids,
        language,
    )


@mandatory_params(["missions", "comment"])
def post_missions_comments(event, context, body):
    """미션게임 댓글 등록
    post_create_comment 수정
    """
    email = event["requestContext"]["authorizer"]["email"]
    game_id = body["missions"]
    comment = body["comment"]

    # 게임 id 체크
    if not mission_module.check_game(game_id):
        raise IdolmasterResourceNotFoundExeption(message="game_id not found")
    game_id = int(game_id)

    target_id = reaction_module.get_reaction_id(game_id=game_id)
    comment_id = reaction_module.create_comment(
        email, target_id, comment
    )
    return {"data": {"comment_id": comment_id}}


@mandatory_params(["missions", "comments"])
def post_missions_comments_likes(event, context, body):
    """미션게임 댓글 추천 등록
    post_like_comment 수정
    """
    email = event["requestContext"]["authorizer"]["email"]
    game_id = body["missions"]
    comment_id = body["comments"]

    # game_id 확인
    if not mission_module.check_game(game_id):
        raise IdolmasterResourceNotFoundExeption(message="game_id not found")
    game_id = int(game_id)

    # comment_id 확인
    comment = reaction_module.get_comment(comment_id)
    if not comment:
        raise IdolmasterResourceNotFoundExeption(
            message="comment_id not found",
            result_code=1)
    comment_id = int(comment_id)

    # check comment in game_id
    reaction_id_game = reaction_module.get_reaction_id(game_id=game_id)
    if comment["target_id"] != reaction_id_game:
        raise IdolmasterBadRequestException(message="Invalid game_id and comment_id")

    target_id = reaction_module.get_reaction_id(comment_id=comment_id)
    reaction_module.submit_like(target_id, email)


@mandatory_params(["missions", "emojis"])
def post_missions_emojis(event, context, body):
    """미션게임 이모지 등록
    post_post_emoji 수정
    """
    email = event["requestContext"]["authorizer"]["email"]
    game_id = body["missions"]
    emoji_id = body["emojis"]

    # game_id 확인
    if not mission_module.check_game(game_id):
        raise IdolmasterResourceNotFoundExeption(message="game_id not found")
    game_id = int(game_id)

    # emoji_id 확인
    emoji_list = reaction_module.list_emoji()
    if emoji_id not in [str(e["emoji_id"]) for e in emoji_list]:
        raise IdolmasterResourceNotFoundExeption(
            message="emoji_id not found",
            result_code=1)
    emoji_id = int(emoji_id)

    target_id = reaction_module.get_reaction_id(game_id=int(game_id))
    reaction_module.submit_emoji(target_id, email, emoji_id)


@mandatory_params(["missions"])
def post_missions_likes(event, context, body):
    """미션게임 추천 등록
    post_like_game 수정
    """
    email = event["requestContext"]["authorizer"]["email"]
    game_id = body["missions"]

    # game_id 확인
    if not mission_module.check_game(game_id):
        raise IdolmasterResourceNotFoundExeption(message="game_id not found")
    game_id = int(game_id)

    target_id = reaction_module.get_reaction_id(game_id=int(game_id))
    reaction_module.submit_like(target_id, email)


@mandatory_params(
    [
        "missions",
        "question_id_1",
        "question_id_2",
        "question_id_3",
        "answer_q1",
        "answer_q2",
        "answer_q3",
    ]
)
def post_missions_submissions(event, context, body):
    """미션게임 미션 질문 제출 및 결과 조회
    post_submit_mission 수정
    """
    game_id = body["missions"]
    qid_1 = body["question_id_1"]
    qid_2 = body["question_id_2"]
    qid_3 = body["question_id_3"]
    aid_1 = body["answer_q1"]
    aid_2 = body["answer_q2"]
    aid_3 = body["answer_q3"]

    # game_id 확인
    if not mission_module.check_game(game_id):
        raise IdolmasterResourceNotFoundExeption(message="game_id not found")
    game_id = int(game_id)

    # 질문 id 확인
    questions = mission_module.list_questions(game_id)
    question_ids = sorted([q["question_id"] for q in questions])
    question_ids_body = sorted(
        [qid_1, qid_2, qid_3]
    )
    if not question_ids == question_ids_body:
        raise IdolmasterResourceNotFoundExeption(
            message="Question ID not found",
            result_code=1)

    ending = mission_module.submit_mission(
        game_id,
        [
            {"question_id": qid_1, "answer": aid_1},
            {"question_id": qid_2, "answer": aid_2},
            {"question_id": qid_3, "answer": aid_3},
        ],
    )
    return {"data": ending}


@mandatory_params(["missions", "comments", "comment"])
def put_missions_comments(event, context, body):
    """미션게임 댓글 수정
    post_update_comment 수정
    exception forbidden 추가
    """
    email = event["requestContext"]["authorizer"]["email"]
    game_id = body["missions"]
    comment_id = body["comments"]
    content = body["comment"]

    # game_id 확인
    if not mission_module.check_game(game_id):
        raise IdolmasterResourceNotFoundExeption(message="game_id not found")
    game_id = int(game_id)

    # comment_id 확인
    comment = reaction_module.get_comment(comment_id)
    if not comment:
        raise IdolmasterResourceNotFoundExeption(
            message="comment_id not found",
            result_code=1)
    comment_id = int(comment_id)

    # check comment in game_id
    reaction_id_game = reaction_module.get_reaction_id(game_id=game_id)
    if comment["target_id"] != reaction_id_game:
        raise IdolmasterBadRequestException(
            message="Invalid game_id and comment_id",
            result_code=1)

    # comment email 확인
    if email != comment["email"]:
        raise IdolmasterForbiddenException

    reaction_module.update_comment(comment_id, content)


#######################################################
# path 시작이 /missions/ 아닌 API
#######################################################


def get_missions_chatroom_backgrounds(event, context, params):
    """미션게임 채팅방 적용 가능한 배경이미지 파일 경로 리스트 조회
    post_list_chatroom_background 수정
    """
    path_list = mission_module.list_chatroom_background()
    return {"data": path_list}


def get_missions_chatroom_bgms(event, context, params):
    """미션게임 채팅방 적용 가능한 bgm 파일 경로 리스트 조회
    post_list_chatroom_bgm 수정
    """
    path_list = mission_module.list_chatroom_bgm()
    return {"data": path_list}


@mandatory_params(["image_file"])
def post_missions_chatroom_backgrounds(event, context, body):
    """미션게임 채팅방 배경화면 등록
    post_upload_chatroom_background 수정
    """
    file_name = mission_module.upload_chatroom_background(body["image_file"])
    return {"data": {"image_file_path": file_name}}


@mandatory_params(["image_file"])
def post_missions_ending_backgrounds(event, context, body):
    """미션게임 엔딩 배경화면 등록
    post_upload_ending_background 수정
    """
    file_name = mission_module.upload_ending_background(body["image_file"])
    return {"data": {"image_file_path": file_name}}
