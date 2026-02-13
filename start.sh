#!/bin/bash

PID_FILE="app.pid"

if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "app 项目已在运行中 (PID: $(cat "$PID_FILE"))"
  exit 1
fi

# 同步依赖
uv sync

# 后台启动
source .venv/bin/activate
nohup gunicorn app.main:app -w 1 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8009 >> app.log 2>&1 &

echo $! > "$PID_FILE"
echo "app 项目已在后台启动 (PID: $!)，日志输出到 app.log"
