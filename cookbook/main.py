from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from loguru import logger

from cookbook.feishu_ws_manager import LarkWebSocketManager

load_dotenv()
lark_ws_manager = LarkWebSocketManager()

from cookbook.fanfou_api import get_access_token


@asynccontextmanager
async def lifespan(app: FastAPI):
    await life_start()

    yield

    await life_end()


async def life_start():
    logger.info("Start...")
    lark_ws_manager.start()


async def life_end():
    logger.info("End...")
    lark_ws_manager.stop()


app = FastAPI(
    title="Hello Cookbook",
    description="FastAPI Hello Cookbook",
    version="1.0.0",
    lifespan=lifespan
)


@app.get("/")
async def root():
    return {"message": "Hello Cookbook!"}


@app.get("/hello")
async def hello():
    return {"message": "FastAPI Cookbook!"}


@app.get("/auth")
async def auth(request: Request, oauth_token: str):
    logger.info(request)
    full_url = str(request.url)  # 完整URL
    logger.info(full_url)
    logger.info(oauth_token)

    result = get_access_token(oauth_token)
    return {"message": result}


