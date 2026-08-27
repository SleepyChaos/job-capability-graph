FROM python:3.11-slim

WORKDIR /srv/backend

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

COPY pyproject.toml README.md ./
COPY app ./app
COPY tools ./tools
COPY migrations ./migrations
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
