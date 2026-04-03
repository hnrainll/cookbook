.PHONY: run dev test install format format-check lint type pyright check

# 启动服务
run:
	uv run uvicorn app.main:app --host 0.0.0.0 --port 8009

# 开发模式（热重载）
dev:
	uv run uvicorn app.main:app --host 0.0.0.0 --port 8009 --reload

# 运行测试
test:
	uv run pytest tests/ -v

# 代码格式化
format:
	uv run ruff format .

# 检查代码格式是否符合 ruff formatter
format-check:
	uv run ruff format --check .

# 静态检查
lint:
	uv run ruff check .

# 类型检查
type:
	uv run ty check

# Pyright 类型检查
pyright:
	uv run pyright

# 本地完整检查
check: format-check lint type test

# 安装依赖
install:
	uv sync
