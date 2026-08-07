# 后端镜像：FastAPI + 统一库（阶段 6 容器化部署）
FROM python:3.12-slim

WORKDIR /app

# 依赖层（利用构建缓存）
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt -i https://mirrors.aliyun.com/pypi/simple/

# 代码与数据
COPY backend/ ./backend/
COPY pipeline/ ./pipeline/
COPY db/ ./db/
COPY scripts/ ./scripts/

EXPOSE 8000

# 与开发环境端口约定一致：宿主机 8002 → 容器 8000（映射见 docker-compose.yml）
CMD ["uvicorn", "backend.api:app", "--host", "0.0.0.0", "--port", "8000"]
