"""
Generic auth and callback routes.
通用授权与回调路由。
"""

from fastapi import APIRouter, Request

router = APIRouter(tags=["auth"])


@router.get("/auth")
async def oauth_callback(request: Request):
    """
    通用 OAuth 回调端点

    接收 platform 和 oauth_token 参数，委托 AuthService 处理。
    URL 格式: /auth?platform=fanfou&oauth_token=xxx
    或兼容旧版: /auth?oauth_token=xxx（默认 platform=fanfou）
    """
    from app.core.auth import AuthService
    from app.core.reply import ReplyService

    platform = request.query_params.get("platform", "fanfou")
    oauth_token = request.query_params.get("oauth_token")
    code = request.query_params.get("code")
    state = request.query_params.get("state")

    if platform == "threads":
        if not code:
            return {"message": "缺少 code 参数"}
        if not state:
            return {"message": "缺少 state 参数"}
    elif not oauth_token:
        return {"message": "缺少 oauth_token 参数"}

    auth_service = AuthService.get_instance()
    if not auth_service:
        return {"message": "AuthService 未初始化"}

    result, user_id = await auth_service.handle_callback(platform, dict(request.query_params))

    if user_id:
        reply_service = ReplyService.get_instance()
        if reply_service:
            from app.schemas.event import MessageSource

            reply_service.send(MessageSource.FEISHU, user_id, result)

    return {"message": result}
