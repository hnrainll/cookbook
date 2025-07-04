#!/bin/bash

# 查找 fanshu 项目的 gunicorn 进程并停止
PIDS=$(ps aux | grep "gunicorn fanshu.main:app" | grep -v grep | awk '{print $2}')

if [ -z "$PIDS" ]; then
  echo "fanshu 项目未运行或未找到其进程。"
else
  echo "正在停止 fanshu 项目 (PIDs: ${PIDS//$'\n'/ })..."
  echo "$PIDS" | xargs kill
  echo "fanshu 项目已停止。"
fi
