# Backend

FastAPI + SQLAlchemy 2 后端，Python 3.11+。当前数据库结构为 Alembic `20260812_0013`，默认运行数据库为 Docker Compose 中的 MySQL 8。

## 本地开发

```bash
cd backend
uv sync --all-groups
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

默认配置见 `.env.example`。通过 `APP_DATABASE_URL` 切换数据库；DeepSeek 使用 `APP_LLM_API_KEY`、`APP_LLM_BASE_URL` 和 `APP_LLM_MODEL`，默认模型为 `deepseek-v4-flash`。密钥不得提交到仓库。

启动后：

- 健康检查：<http://127.0.0.1:8000/api/v1/health>
- OpenAPI：<http://127.0.0.1:8000/docs>

## 质量检查

```bash
uv run ruff check app tests tools migrations
uv run pytest --cov
```

## 常用数据任务

所有命令均从 `backend/` 执行。参数和完整数据链路见项目文档，不要直接执行外部数据包中的 SQL。

```bash
# 解析 JD
uv run python -m tools.parse_jobs \
  --taxonomy-version v1.1 --target-date 2026-08-10

# 聚类（替换为解析命令返回的 run_code）
uv run python -m tools.cluster_jobs \
  --parse-run-code jdparse_8ad8184577692c219c983899

# DeepSeek 小批量、只审计不回写
uv run python -m tools.reassess_technologies_llm \
  --parse-run-code jdparse_8ad8184577692c219c983899 \
  --limit 24 --batch-size 12 --no-apply
```

技术主数据和 JD 的完整空库重建已经固化在根目录 `docker-compose.yml` 的 `bootstrap` 服务中。优先使用：

```bash
cd ..
RESTORE_RUNTIME_SNAPSHOT=0 docker compose up --build -d
```

## 文档

- [MVP 现状与边界](../docs/01-MVP现状与边界.md)
- [系统架构与数据流](../docs/02-系统架构与数据流.md)
- [数据与核心算法](../docs/03-数据与核心算法.md)
- [测试、部署与运维](../docs/04-测试部署与运维.md)
- [开发组任务清单](../docs/05-开发组任务清单.md)

接口参数和响应模型以运行时 OpenAPI 为准，避免在本文件重复维护路由清单。
