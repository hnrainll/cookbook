"""
Media routes.
媒体文件只读访问路由。
"""

from mimetypes import guess_type
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

router = APIRouter(tags=["media"])

IMAGE_DIR = Path("data/images")


@router.get("/media/images/{filename}")
async def get_image(filename: str):
    path = IMAGE_DIR / filename
    if path.name != filename or not path.is_file():
        raise HTTPException(status_code=404, detail="Image not found")

    media_type, _encoding = guess_type(path.name)
    return FileResponse(path, media_type=media_type or "application/octet-stream")
