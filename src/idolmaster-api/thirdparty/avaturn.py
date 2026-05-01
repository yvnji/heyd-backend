"""Avaturn API"""

import const
from lib.http_request import request


avaturn_api_url = "https://api.avaturn.me/api/v1"
headers = {
    "Content-type": "application/json; charset=UTF-8;",
    "Authorization": f"Bearer {const.AVATURN_ACCESS_TOKEN}",
    "Accept": "application/json; charset=UTF-8;",
}


def create_export(avatar_id: str) -> dict:
    """Exports a specified avatar.

    :param avatar_id: avatar ID

    :return
        {
            'status_code': int
            'response': {
                'status': str,  (pending || ready || failed)
                'url': str | None   (Exported model URL if status='ready', otherwise null)
            }
        }
    """
    path = f"/exports/new?avatar_id={avatar_id}"
    url = avaturn_api_url + path
    return request("POST", url, headers=headers)


def create_user() -> dict:
    """Creates new avaturn user.
    Users are anonymous, no personal user data is needed.

    :return
        {
            'status_code': int
            'response': {
                'id': str (user ID)
            }
        }
    """
    path = "/users/new"
    url = avaturn_api_url + path
    return request("POST", url, headers=headers)


def delete_user(user_id: str) -> dict:
    """Deletes user and all it's data, including uploaded photos, avatars, cached exports etc.

    :param user_id: user ID

    :return
        {
            'status_code': int
            'response': None
        }
    """
    path = f"/users/{user_id}"
    url = avaturn_api_url + path
    return request("DELETE", url, headers=headers)


def delete_user_avatar(user_id: str, avatar_id: str) -> dict:
    """Delete avatar owned by user.
    Deletes all corresponding data, including cached export models.

    :param user_id: user ID
    :param avatar_id: avatar ID

    :return
        {
            'status_code': int
            'response': None
        }
    """
    path = f"users/{user_id}/avatars/{avatar_id}"
    url = avaturn_api_url + path
    return request("DELETE", url, headers=headers)


def get_customization(id: str) -> dict:
    """Get current avatar customization.

    :param id: customization ID

    :return
        {
            'status_code': int
            'response': response object (res. https://docs.avaturn.me/api/#/operations/get_customization_api_v1_avatars__id__customization_get)
        }
    """
    path = f"/avatars/{id}/customization"
    url = avaturn_api_url + path
    return request("GET", url, headers=headers)


def list_user_avatars(user_id: str) -> dict:
    """List user avatars.

    :param user_id: user ID

    :return
        {
            'status_code': int
            'response': [
                {
                    'id': str,  (Avatar ID)
                    'status': str   (Allowed values : pending || processing || ready || failed)
                },
                ...
            ]
        }
    """
    path = f"/users/{user_id}/avatars"
    url = avaturn_api_url + path
    return request("GET", url, headers=headers)


def new_avatar(user_id: str) -> dict:
    """Create new avatar for given user from images.

    :param user_id: user ID

    :return
        {
            'status_code': int
            'response': {
                'avatar_id': str,   (Avatar ID)
                'upload_url': str   (URL for upload)
            }
        }
    """
    path = "/avatars/new"
    url = avaturn_api_url + path
    body = {"user_id": user_id}
    return request("POST", url, headers=headers, data=body)


def new_session(user_id: str, avatar_id: str = None) -> dict:
    """Create new avatar for given user from images.

    :param user_id: user ID
    :param avatar_id: avatar ID

    :return
        {
            'status_code': int
            'response': {
                'url': str,
                'id': str,   (session id)
                'custom_upload_url: str | None  (Deprecated. Do not use.)
            }
        }
    """
    path = "/sessions/new"
    url = avaturn_api_url + path
    body = {"user_id": user_id, "config": {"type": "edit_existing"}}
    if avatar_id:
        body["config"]["avatar_id"] = avatar_id
    return request("POST", url, headers=headers, data=body)


def render_user_avatar_async(avatar_id: str) -> dict:
    """Renders a scene with specified avatar.

    :param avatar_id: avatar ID

    :return
        {
            'status_code': int
            'response': {
                'id': str,
                'status': str,  (pending || ready || failed),
                'render_url': str
            }
        }
    """
    path = f"/renders/new?avatar_id={avatar_id}&scene=common/transparent_half_body&format=jpg"
    url = avaturn_api_url + path
    return request("POST", url, headers=headers)


def set_customization(id: str, asset_dict: dict) -> dict:
    """Set avatar customization.

    :param id: customization ID
    :param asset_dict: object of asset (ref. https://docs.avaturn.me/api/#/operations/set_customization_api_v1_avatars__id__customization_put)

    :return
        {
            'status_code': int
            'response': None
        }
    """
    path = f"/avatars/{id}/customization"
    url = avaturn_api_url + path
    return request("POST", url, headers=headers, data=asset_dict)
