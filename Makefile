.PHONY: run dev test install

# 启动服务
run:
	uv run uvicorn app.main:app --host 0.0.0.0 --port 8009

# 开发模式（热重载）
dev:
	uv run uvicorn app.main:app --host 0.0.0.0 --port 8009 --reload

# 运行测试
test:
	uv run pytest tests/ -v

# 安装依赖
install:
	uv sync
