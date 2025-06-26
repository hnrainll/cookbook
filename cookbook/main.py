from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from loguru import logger

from cookbook.feishu_ws_manager import LarkWebSocketManager

from cookbook.fanfou_api import gen_auth_url

load_dotenv()
lark_ws_manager = LarkWebSocketManager()


gen_auth_url()


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
async def auth(request: Request):
    logger.info(request)
    full_url = str(request.url)  # 完整URL
    logger.info(full_url)
    return {"message": "Cookbook Auth!"}

