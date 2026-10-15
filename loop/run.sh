#!/usr/bin/env bash
# 启动闸门操作台 + 长任务看板（单机单用户）。
#
# 这里启动的端口**不是** DSH Web GUI；它是本闭环自己的界面。
set -euo pipefail
cd "$(dirname "$0")"
PORT="${LOOP_PORT:-8099}"
exec .venv/bin/python -m uvicorn services.api:app --app-dir . --host 127.0.0.1 --port "$PORT"
