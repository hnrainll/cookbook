"""
Feishu Webhook Handler for FastAPI
飞书 Webhook 处理器 - 用于接收飞书事件回调

这个模块提供 FastAPI 路由处理函数，用于：
1. 接收飞书服务器的事件回调
2. 验证请求签名（安全性）
3. 将事件转发给飞书管理器处理
"""

from fastapi import APIRouter, Request, Response
from loguru import logger

router = APIRouter()


@router.get("/auth")
async def fanfou_auth(request: Request) -> Response:
    """
    饭否授权

    饭否授权回调端点

    Args:
        request: FastAPI 请求对象

    Returns:
        响应对象
    """
    try:
        # 获取原始请求体
        body = await request.body()

        logger.debug(f"Received Feishu webhook: {len(body)} bytes")

        # TODO: 验证签名（生产环境必须）
        # if not verify_signature(body, headers):
        #     logger.warning("Invalid Feishu webhook signature")
        #     return Response(status_code=401)

        # 解析 JSON
        import json

        data = json.loads(body)

        # 处理 URL 验证挑战
        # 飞书配置 Webhook 时会发送验证请求
        if "challenge" in data:
            logger.info("Received Feishu URL verification challenge")
            return Response(
                content=json.dumps({"challenge": data["challenge"]}),
                media_type="application/json",
            )

        # 正常事件处理
        # 注意：这里只是接收，真正的处理在 FeishuManager 的独立线程中
        logger.info(f"Received Feishu event: {data.get('type', 'unknown')}")

        # 快速返回响应（飞书要求 3 秒内响应）
        return Response(content=json.dumps({"code": 0}), media_type="application/json")

    except Exception as e:
        logger.error(f"Error handling Feishu webhook: {e}", exc_info=True)
        return Response(status_code=500)
