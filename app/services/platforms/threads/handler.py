"""
Threads callback routes.
Threads 平台回调路由。
"""

from fastapi import APIRouter, Request

router = APIRouter(tags=["threads"])


@router.get("/callback/threads")
async def threads_callback(request: Request):
    """
    Threads 管理回调端点

    当前只做轻量确认响应。
    URL 格式: /callback/threads?type=uninstall
    """
    return {"message": "ok"}
