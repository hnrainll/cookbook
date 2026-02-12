#!/bin/bash

PID_FILE="app.pid"

if [ ! -f "$PID_FILE" ]; then
  echo "PID 文件不存在，app 项目可能未运行。"
  exit 1
fi

PID=$(cat "$PID_FILE")

if kill -0 "$PID" 2>/dev/null; then
  echo "正在停止 app 项目 (PID: $PID)..."
  kill "$PID"
  rm -f "$PID_FILE"
  echo "app 项目已停止。"
else
  echo "进程 $PID 不存在，清理 PID 文件。"
  rm -f "$PID_FILE"
fi
