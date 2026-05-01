from lib.decorator import mandatory_params
from service import render as render_module


@mandatory_params(["avatar_id", "event", "status"])
def post_render_ready(event, context, body):
    """Avaturn에서 Webhook으로 사용"""
    return render_module.ready(
        body["avatar_id"],
        body["event"],
        body["status"],
        body.get("render_url"),
        body.get("export_url"),
    )
