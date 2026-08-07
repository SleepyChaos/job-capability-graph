#!/bin/bash
# 一键启动开发环境：后端 API（FastAPI，:8002）+ 前端（Next.js，:3000）
# 注：8000/8001 常被并行开发的其他项目占用，本项目后端默认使用 8002（可用 API_PORT 覆盖）
# 前置：已运行 python3 -m pipeline.run_pipeline 生成 unified.db
set -euo pipefail

API_PORT="${API_PORT:-8002}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [ ! -f db/unified.db ]; then
  echo "未找到 db/unified.db，先运行数据管线..."
  python3 -m pipeline.run_pipeline --reset
fi

# 后端 API
if lsof -nP -iTCP:"$API_PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "后端 API 已在 :$API_PORT 运行"
else
  echo "启动后端 API（:$API_PORT）..."
  .venv/bin/uvicorn backend.api:app --port "$API_PORT" > /tmp/jcg_api.log 2>&1 &
  sleep 2
fi

# 前端
echo "启动前端（:3000）..."
cd "$ROOT/frontend"
PORT=3000 pnpm exec next dev --port 3000
