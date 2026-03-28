"""
Feishu Webhook Handler & OAuth Callback
飞书 Webhook + 通用 OAuth 回调路由
"""

import json

from fastapi import APIRouter, Request, Response
from loguru import logger

router = APIRouter(tags=["webhook"])


@router.post("/webhook/feishu")
async def feishu_webhook(request: Request) -> Response:
    """飞书事件回调端点（URL 验证用）"""
    try:
        body = await request.body()
        data = json.loads(body)

        if "challenge" in data:
            logger.info("Received Feishu URL verification challenge")
            return Response(
                content=json.dumps({"challenge": data["challenge"]}),
                media_type="application/json",
            )

        logger.info(f"Received Feishu event: {data.get('type', 'unknown')}")
        return Response(content=json.dumps({"code": 0}), media_type="application/json")

    except Exception as e:
        logger.error(f"Error handling Feishu webhook: {e}", exc_info=True)
        return Response(status_code=500)


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

    oauth_token = request.query_params.get("oauth_token")
    platform = request.query_params.get("platform", "fanfou")

    if not oauth_token:
        return {"message": "缺少 oauth_token 参数"}

    auth_service = AuthService.get_instance()
    if not auth_service:
        return {"message": "AuthService 未初始化"}

    result, user_id = await auth_service.handle_callback(platform, dict(request.query_params))

    # 通过 ReplyService 通知用户
    if user_id:
        reply_service = ReplyService.get_instance()
        if reply_service:
            from app.schemas.event import MessageSource

            reply_service.send(MessageSource.FEISHU, user_id, result)

    return {"message": result}
