from contextlib import asynccontextmanager

from fastapi import FastAPI
from loguru import logger

from cookbook.feishu_bot import lark_ws_client

@asynccontextmanager
async def lifespan(app: FastAPI):
    await life_start()

    yield

    await life_end()


# 创建 FastAPI 应用实例
app = FastAPI(
    title="Hello Cookbook",
    description="一个简单的 FastAPI Hello Cookbook 示例",
    version="1.0.0",
    lifespan=lifespan
)

async def life_start():
    logger.info("Start...")
    await lark_ws_client.start()


async def life_end():
    logger.info("End...")


@app.get("/")
async def root():
    """根路径 - 最基础的 Hello World"""
    return {"message": "Hello Cookbook!"}


import sys
logger.info(sys.path)