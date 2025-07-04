#!/bin/bash

# 激活 uv 虚拟环境
source .venv/bin/activate

# 后台启动 fanshu 项目
nohup gunicorn fanshu.main:app -w 1 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8009 >> fanshu.log 2>&1 &

echo "fanshu 项目已在后台启动，日志输出到 fanshu.log"
