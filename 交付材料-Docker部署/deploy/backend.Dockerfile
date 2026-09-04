FROM python:3.11-slim

WORKDIR /srv/backend

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple

COPY pyproject.toml README.md ./
COPY app ./app
COPY tools ./tools
COPY migrations ./migrations
# 人岗匹配的岗位图谱桥接表（job_graph_bridge.json）就在这里。漏拷不会报错——
# load_job_graph_bridge() 找不到文件时静默返回空表，于是匹配详情里的「岗位图谱
# 关联」对每个岗位都显示「尚未关联」，看起来像功能没做。
COPY data ./data
COPY alembic.ini ./

ARG PIP_ALLOW_INSECURE_INDEX=0
RUN pip install --upgrade pip && \
    if [ "$PIP_ALLOW_INSECURE_INDEX" = "1" ]; then \
      PIP_TRUSTED_HOST='pypi.org files.pythonhosted.org' \
        pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org .; \
    else \
      pip install .; \
    fi

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=4)" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
