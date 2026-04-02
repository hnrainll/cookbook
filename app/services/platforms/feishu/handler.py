"""
Feishu Webhook Handler
飞书 Webhook 路由
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
