FROM python:3.11-slim

WORKDIR /srv/backend

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

COPY pyproject.toml README.md ./
COPY app ./app
COPY tools ./tools
COPY migrations ./migrations
COPY alembic.ini ./

RUN pip install --upgrade pip && pip install .

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=4)" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
