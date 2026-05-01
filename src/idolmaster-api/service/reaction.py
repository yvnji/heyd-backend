import json

from lib import time
from lib.decorator import preprocessing_cursor
from thirdparty.mariadb import get_db_connection


@preprocessing_cursor
def cancel_block(target_id: int, user_id: int, cursor: object = None) -> None:
    """숨기기 취소

    :param target_id: reaction_target 테이블에 등록된 id
    :param user_id: 등록한 계정 ID
    :param cursor: pymysql.connect().cursor()
    """
    query = f"""
    DELETE FROM `block`
    WHERE
        user_id = {user_id}
        AND target_id = {target_id}
    """
    cursor.execute(query)


@preprocessing_cursor
def cancel_emoji(
    target_id: int, email: str, emoji_id: int, cursor: object = None
) -> None:
    """이모지 등록 취소

    :param target_id: reaction_target 테이블에 등록된 id
    :param email: 좋아요 등록한 계정 email
    :param emoji_id: emoji id
    :param cursor: pymysql.connect().cursor()
    """

    query = f"""
    DELETE FROM `emoji_reaction`
    WHERE
        email = '{email}'
        AND target_id = {target_id}
        AND emoji_id = {emoji_id}
    """

    cursor.execute(query)


@preprocessing_cursor
def cancel_like(target_id: int, email: str, cursor: object = None) -> None:
    """좋아요 취소

    :param target_id: reaction_target 테이블에 등록된 id
    :param email: 좋아요 등록한 계정 email
    :param cursor: pymysql.connect().cursor()
    """

    query = f"""
    DELETE FROM `like`
    WHERE
        email = '{email}'
        AND target_id = {target_id}
    """
    cursor.execute(query)


@preprocessing_cursor
def check_like_by_email(target_id: int, email: str, cursor: object = None) -> bool:
    """사용자가 좋아요 했는지 체크"""
    ch = False
    query = f"""
    SELECT 1
    FROM `like`
    WHERE target_id = {target_id} AND email = '{email}'
    """
    cursor.execute(query)
    data = cursor.fetchone()
    ch = True if data else False
    return ch


@preprocessing_cursor
def create_comment(
    email: str, target_id: int, comment: str, cursor: object = None
) -> int:
    """댓글 등록

    :param email: 댓글 등록할 계정 email
    :param target_id: reaction_target 테이블에 등록된 id
    :param comment: 댓글 내용
    :param cursor: pymysql.connect().cursor()

    :return: 생성된 댓글 id
    """

    query = f"""
    INSERT INTO `comment` (email, target_id, comment)
    VALUES ('{email}', {target_id}, '{comment}')
    RETURNING id
    """
    cursor.execute(query)
    comment_id = cursor.fetchone()["id"]

    # reaction_target 데이터 생성
    create_reaction_target(comment_id=comment_id, cursor=cursor)

    return comment_id


@preprocessing_cursor
def create_reaction_target(
    character_id: str = None,
    comment_id: int = None,
    game_id: int = None,
    content_id: int = None,
    bgm_id: int = None,
    cursor: object = None,
) -> int:
    """reaction_target 테이블에 데이터 생성

    :param character_id: 캐릭터 id
    :param comment_id: 댓글 Id
    :param game_id: 미션게임 id
    :param content_id: 컨텐츠 ID
    :param bgm_id: bgm ID
    :param cursor: pymysql.connect().cursor()

    :return: 생성된 target id
    """

    key = ""
    value = ""
    if character_id:
        key = "character_id"
        value = f"'{character_id}'"
    elif comment_id:
        key = "comment_id"
        value = comment_id
    elif game_id:
        key = "game_id"
        value = game_id
    elif content_id:
        key = "content_id"
        value = content_id
    elif bgm_id:
        key = "bgm_id"
        value = bgm_id
    query = f"""
    INSERT INTO `reaction_target` ({key})
    VALUES ({value})
    RETURNING id
    """
    cursor.execute(query)
    target_id = cursor.fetchone()["id"]

    return target_id


@preprocessing_cursor
def create_tag(target_id: int, tag_list: list, cursor: object = None) -> None:
    """태그 생성"""
    query_values = []
    query_params = []
    timestamp_at = time.timestampnow()
    for tag in tag_list:
        query_values.append("(%s, %s, %s)")
        query_params.extend([tag, target_id, time.fromtimestamp(timestamp_at)])
        timestamp_at += 1
    query_values = ", ".join(query_values)
    query = f"""
    INSERT INTO `tag` (tag, target_id, created_at)
    VALUES {query_values}
    ON DUPLICATE KEY UPDATE
        tag = tag
    """
    cursor.execute(query, query_params)


@preprocessing_cursor
def delete_comment(comment_id: int, cursor: object = None) -> None:
    """댓글 삭제

    :param comment_id: 댓글 id
    :param cursor: pymysql.connect().cursor()
    """

    query = f"""
    DELETE FROM `comment`
    WHERE
        id = {comment_id}
    """
    cursor.execute(query)


@preprocessing_cursor
def delete_tag(target_id: int, tag_list: list = None, cursor: object = None) -> None:
    """태그 삭제"""
    query_where = []
    query_where.append(f"target_id = {target_id}")
    if tag_list:
        tag_list = [json.dumps(t) for t in tag_list]
        tags_str = ", ".join(tag_list)
        query_where.append(f"tag in ({tags_str})")
    query_where = " AND ".join(query_where)
    query = f"""
    DELETE FROM `tag`
    WHERE {query_where}
    """
    cursor.execute(query)


@preprocessing_cursor
def get_block(target_id: int, user_id: int, cursor: object = None) -> bool:
    """숨기기 상태 조회

    :param target_id: reaction_target 테이블에 등록된 id
    :param user_id: 계정 ID
    :param cursor: pymysql.connect().cursor()

    :return: 숨기기 등록 유무
    """
    query = f"SELECT * FROM `block` WHERE user_id={user_id} AND target_id={target_id}"
    cursor.execute(query)
    res = cursor.fetchone()
    return True if res else False


@preprocessing_cursor
def get_comment(
    comment_id: int = None,
    cursor: object = None
) -> bool:
    """댓글 데이터 조회

    :param comment_id: 댓글 id
    :param cursor: pymysql.connect().cursor()

    :return: comment 테이블 데이터
    """
    query = "SELECT * FROM `comment` WHERE active = 1 AND id = %s"
    cursor.execute(query, (comment_id))
    return cursor.fetchone()


@preprocessing_cursor
def get_emoji_status(target_id: int, email: str, emoji_id: int, cursor: object = None) -> bool:
    """현재 이모지 상태 조회

    :return
        True: 이모지 등록
        False: 이모지 등록 X
    """
    query = f"""
        SELECT 1
        FROM `emoji_reaction`
        WHERE
            email = '{email}'
            AND target_id = {target_id}
            AND emoji_id = {emoji_id}
    """
    cursor.execute(query)
    return True if cursor.fetchone() else False


@preprocessing_cursor
def get_like_count(target_id: int, cursor: object = None) -> int:
    """좋아요 수 조회"""
    cnt = 0
    query = f"SELECT 1 FROM `like` WHERE target_id = {target_id}"
    cursor.execute(query)
    cnt = len(cursor.fetchall())
    return cnt


@preprocessing_cursor
def get_like_status(target_id: int, email: str, cursor: object = None) -> bool:
    """현재 좋아요 상태 조회

    :return
        True: 좋아요 등록
        False: 좋아요 등록 X
    """
    query = f"SELECT 1 FROM `like` WHERE email = '{email}' AND target_id = {target_id}"
    cursor.execute(query)
    return True if cursor.fetchone() else False


@preprocessing_cursor
def get_reaction_id(
    character_id: str = None,
    comment_id: int = None,
    game_id: int = None,
    content_id: int = None,
    bgm_id: int = None,
    cursor: object = None,
) -> int:
    """reaction_target 테이블에 등록된 target id 조회"""
    # 제약 조건
    if (
        sum(origin_id is not None for origin_id in [character_id, comment_id, game_id, content_id, bgm_id])
        != 1
    ):
        raise Exception(f"invalid resources reaction.get_reaction_id (params : {locals()})")

    where_query = ""
    if character_id:
        where_query = f"character_id = '{character_id}'"
    elif comment_id:
        where_query = f"comment_id = {comment_id}"
    elif game_id:
        where_query = f"game_id = {game_id}"
    elif content_id:
        where_query = f"content_id = {content_id}"
    elif bgm_id:
        where_query = f"bgm_id = {bgm_id}"

    query = f"""
    SELECT
        id
    FROM
        `reaction_target`
    WHERE
        {where_query}
    """
    cursor.execute(query)
    res = cursor.fetchone()

    if not res:
        res = {
            "id": create_reaction_target(
                character_id=character_id,
                comment_id=comment_id,
                game_id=game_id,
                content_id=content_id,
                bgm_id=bgm_id,
                cursor=cursor
            )
        }

    return res["id"]


def get_total_comments(target_id: int) -> int:
    """모든 댓글 조회"""
    comments = []
    query = f"""
    SELECT *
    FROM `comment`
    WHERE target_id = {target_id}
    """
    db_connection = get_db_connection()
    with db_connection as db:
        cursor = db.cursor()
        cursor.execute(query)
        comments = cursor.fetchall()
    return comments


@preprocessing_cursor
def list_comments(
    target_id: int,
    email: str,
    sort_by: str = None,
    page_size: int = None,
    offset: int = None,
    cursor: object = None,
) -> list:
    """댓글 리스트 조회

    :param target_id: reaction_target 테이블에 등록된 조회 할 target_id
    :param email: 댓글 등록 확인 할 email
    :param sort_by: 댓글 정렬 기준 (newest : 최신순(default), top : 추천순)
    :param page_size: 조회할 데이터 길이
    :param offset: offset
    :param cursor: pymysql.connect().cursor()

    :return
        [
            {
                'comment_id': int,  (댓글 Id)
                'content': str,  (댓글 내용)
                'created_time': datatime,  (댓글 등록 시간)
                'like_count': int, (좋아요 수)
                'writer': str,  (댓글 등록한 계정 사용자 이름)
                'is_liked': bool,  (parameter email 계정 사용자가 좋아요 등록했는지 확인)
                'is_writer': bool,  (parameter email 계정 사용자가 댓글 등록했는지 확인)
            }
        ]
    """

    comments = []
    sort_query = ""
    if sort_by == "newest" or not sort_by:
        sort_query = ""
    elif sort_by == "top":
        sort_query = "like_count DESC, "

    pagination_query = ""
    if page_size and offset:
        pagination_query = f"LIMIT {page_size} OFFSET {offset}"

    query = f"""
    SELECT
        comment.id AS comment_id,
        comment.comment AS content,
        comment.created_time,
        COALESCE(like_count_alias.like_count, 0) AS like_count,
        user.name AS writer,
        CASE
            WHEN (is_liked_alias.email IS NOT NULL) THEN TRUE
            ELSE FALSE
        END AS is_liked,
        CASE
            WHEN (comment.email = '{email}') THEN TRUE
            ELSE FALSE
        END AS is_writer
    FROM
        `comment`
    LEFT JOIN
        `reaction_target`
        ON comment.id = reaction_target.comment_id
    LEFT JOIN
        (
            SELECT
                COUNT(*) as like_count,
                target_id
            FROM
                `like`
            GROUP BY
                target_id
        ) AS like_count_alias
        ON like_count_alias.target_id = reaction_target.id
    LEFT JOIN
        (
            SELECT
                target_id,
                email
            FROM
                `like`
            WHERE
                email = '{email}'
        ) AS is_liked_alias
        ON is_liked_alias.target_id = reaction_target.id
    JOIN
        `user`
        ON user.email = comment.email
    WHERE
        comment.target_id = {target_id}
    ORDER BY {sort_query}created_time DESC
    {pagination_query}
    """
    cursor.execute(query)
    comments = cursor.fetchall()
    return comments


@preprocessing_cursor
def list_emoji(cursor: object = None) -> list:
    """사용 가능한 모든 이모지 조회

    :param cursor: pymysql.connect().cursor()

    :return
        [
            {
                'emoji_id': int,
                'emoji': str
            }
        ]
    """
    query = """SELECT emoji_id, emoji FROM `emoji`"""
    cursor.execute(query)
    return cursor.fetchall()


@preprocessing_cursor
def list_emoji_registered(target_id: int, email: str, cursor: object = None) -> list:
    """사용된 이모지 리스트 조회.
    target_id에 등록된 모든 이모지 조회.
    count 내림차순 정렬

    :param target_id: reaction_target 테이블에 등록된 조회 할 target_id
    :param email: 이모지 등록했는지 확인 할 email
    :param cursor: pymysql.connect().cursor()

    :return
        [
            {
                'emoji_id': int,
                'emoji_type': str (이모지 이름),
                'count': int (해당 이모지 등록한 수),
                'is_clicked': bool (email 계정이 해당 이모지를 등록했는지 확인)
            },
            ...
        ]
    """

    emoji_dict = dict()

    # 이모지 수 확인
    query_emoji = f"""
        SELECT
            E.emoji,
            E.emoji_id,
            COUNT(ER.email) AS count
        FROM `emoji_reaction` AS ER
        JOIN `emoji` AS E ON E.emoji_id = ER.emoji_id
        WHERE ER.target_id = {target_id}
        GROUP BY E.emoji
    """
    cursor.execute(query_emoji)
    emoji_dict = {
        e["emoji_id"]: {"emoji_type": e["emoji"], "count": e["count"], "is_clicked": False}
        for e in cursor.fetchall()
    }

    # 사용자 이모지 확인
    query_user_emoji = f"""
    SELECT E.emoji, E.emoji_id
    FROM `emoji_reaction` AS ER
    JOIN `emoji` AS E ON E.emoji_id = ER.emoji_id
    WHERE
        ER.target_id = {target_id}
        AND ER.email = '{email}'
    """
    cursor.execute(query_user_emoji)
    for e in cursor.fetchall():
        emoji_dict[e["emoji_id"]]["is_clicked"] = True

    return sorted([
        {
            "emoji_id": eid,
            "emoji_type": emoji_dict[eid]["emoji_type"],
            "count": emoji_dict[eid]["count"],
            "is_clicked": emoji_dict[eid]["is_clicked"],
        }
        for eid in emoji_dict
    ], key=lambda r: r["count"], reverse=True)


@preprocessing_cursor
def list_tag(target_id: int, cursor: object = None) -> list:
    """태그 리스트 조회"""
    query = f"""
    SELECT
        tag,
        created_at
    FROM `tag`
    WHERE target_id = {target_id}
    """
    cursor.execute(query)
    data = cursor.fetchall()
    return data if data else []


@preprocessing_cursor
def submit_block(target_id: int, user_id: int, cursor: object = None) -> None:
    """숨기기 등록

    :param target_id: reaction_target 테이블에 등록된 id
    :param user_id: 등록할 계정 ID
    :param cursor: pymysql.connect().cursor()
    """
    query = f"""
    INSERT INTO `block` (user_id, target_id)
    VALUES
        ({user_id}, {target_id})
    """
    cursor.execute(query)


@preprocessing_cursor
def submit_emoji(
    target_id: int, email: str, emoji_id: int, cursor: object = None
) -> None:
    """이모지 등록

    :param target_id: reaction_target 테이블에 등록된 id
    :param email: 이모지 등록할 계정 email
    :param emoji_id: 이모지 id
    :param cursor: pymysql.connect().cursor()
    """

    query = f"""
    INSERT INTO `emoji_reaction` (target_id, email, emoji_id)
    VALUES ({target_id}, '{email}', {emoji_id})
    """
    cursor.execute(query)


@preprocessing_cursor
def submit_like(target_id: int, email: str, cursor: object = None) -> None:
    """좋아요 등록

    :param target_id: reaction_target 테이블에 등록된 id
    :param email: 좋아요 등록할 계정 email
    :param cursor: pymysql.connect().cursor()
    """

    query = f"""
    INSERT INTO `like` (email, target_id)
    VALUES
        ('{email}', {target_id})
    ON DUPLICATE KEY UPDATE
        email = '{email}'
    """
    cursor.execute(query)


@preprocessing_cursor
def submit_report(target_id: int, user_id: int, detail: str, cursor: object = None) -> None:
    """신고 등록

    :param target_id: reaction_target 테이블에 등록된 id
    :param user_id: 신고한 계정 ID
    :param detail: 신고 내용
    :param cursor: pymysql.connect().cursor()
    """
    query = f"""
    INSERT INTO `report` (user_id, target_id, detail)
    VALUES
        ({user_id}, {target_id}, '{detail}')
    """
    cursor.execute(query)


@preprocessing_cursor
def update_comment(comment_id: int, comment: str, cursor: object = None) -> None:
    """댓글 편집

    :param comment_id: 댓글 id
    :param comment: 수정 할 댓글 내용
    :param cursor: pymysql.connect().cursor()
    """

    query = f"""
    UPDATE `comment`
    SET
        comment = '{comment}'
    WHERE
        id = {comment_id}
    """
    cursor.execute(query)
