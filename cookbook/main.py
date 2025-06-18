from fastapi import FastAPI

# 创建 FastAPI 应用实例
app = FastAPI(
    title="Hello World API",
    description="一个简单的 FastAPI Hello World 示例",
    version="1.0.0"
)

@app.get("/")
async def root():
    """根路径 - 最基础的 Hello World"""
    return {"message": "Hello Cookbook!"}
