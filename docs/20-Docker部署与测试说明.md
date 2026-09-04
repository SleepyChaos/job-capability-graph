# Docker 部署与单元测试说明

> 对应赛题「软件模块」交付项：源代码、可执行程序、部署（Dockerfile / 容器化部署）说明、单元测试用例（覆盖率 ≥ 60%）。
> 本文只写经实测跑通的步骤；踩过的坑一并记下，评审照做能起来。

## 1. 交付物对照

| 赛题要求 | 本项目对应物 |
| --- | --- |
| 源代码（可提供开源链接 / 私有仓库开放评审权限） | `https://github.com/SleepyChaos/job-capability-graph` |
| 可执行程序 | 容器镜像三件套：`backend`（FastAPI）、`frontend`（Nginx 静态站）、`mysql`；`docker compose up` 即为可执行形态 |
| 部署说明（Dockerfile / 容器化部署） | [`backend/Dockerfile`](../backend/Dockerfile)、[`frontend/Dockerfile`](../frontend/Dockerfile)、[`docker-compose.yml`](../docker-compose.yml)，步骤见下文第 3 节 |
| 单元测试用例（覆盖率 ≥ 60%） | `backend/tests/` 共 38 个测试文件；`pyproject.toml` 中 `fail_under = 60`，低于该线直接判失败。跑法见第 5 节 |

## 2. 环境要求

- Docker Desktop（Windows / macOS）或 Docker Engine + Compose v2（Linux）
- 磁盘 ≥ 10 GB：MySQL 数据卷、镜像与 39 MB 的图谱产物
- 内存 ≥ 4 GB
- 首次构建需要拉取 `python:3.11-slim`、`node:22-alpine`、`nginx:1.27-alpine`、`mysql:8.0`；镜像内的 pip / npm 已指向国内源（清华 PyPI、npmmirror）

## 3. 一键启动

```bash
git clone https://github.com/SleepyChaos/job-capability-graph.git
cd job-capability-graph
docker compose up -d backend frontend
```

`docker-compose.yml` 已把依赖顺序编排好，`up` 一次会依次完成：

| 服务 | 作用 | 结束条件 |
| --- | --- | --- |
| `mysql` | MySQL 8.0，数据落在命名卷 `mysql-data` | healthcheck 通过 |
| `restore` | 首次启动时恢复仓库内已审计的运行快照（`data/runtime/*.sql.gz.part-*`）；库里已有表则跳过 | 运行一次即退出 |
| `migrate` | `alembic upgrade head` | 运行一次即退出 |
| `bootstrap` | 从核心 XLSX 重建技术词体系与岗位数据，并跑解析、聚类、审批 | 运行一次即退出 |
| `backend` | FastAPI，`0.0.0.0:8000` | 常驻 |
| `frontend` | Nginx 静态站 + `/api` 反代到 `backend:8000` | 常驻 |

启动后：

- 平台界面 <http://localhost:8080>
- 接口文档 <http://localhost:8000/docs>
- 健康检查 <http://localhost:8000/api/v1/health>

跳过快照恢复、完全从 XLSX 重建：

```bash
RESTORE_RUNTIME_SNAPSHOT=0 docker compose up -d backend frontend
```

## 4. 两个已知坑

**一、Windows 端口保留。** Docker Desktop 重启后，Windows 可能把 `8043–8242`（含 8080）整段划入保留端口，容器绑定会报 `An attempt was made to access a socket in a way forbidden by its access permissions`。先查保留段：

```bash
netsh int ipv4 show excludedportrange protocol=tcp
```

避开保留段改用其他端口（例如 8300），改 `docker-compose.yml` 中 `frontend` 的端口映射为 `"8300:80"` 即可；`/api` 是容器内反代，换宿主端口不影响接口。

**二、LLM 网关默认不开。** 新岗位候选的表达层与五维画像生成需要 LLM；未配置时全部降级为规则输出，功能不报错但文案质量下降。密钥只从**未入库**的 `.env` 注入（`.gitignore` 已覆盖）：

```bash
# 项目根目录 .env
APP_LLM_API_KEY=<你的密钥>
APP_LLM_BASE_URL=https://<网关地址>/compatible-mode/v1
APP_LLM_MODEL=qwen3.7-flash
APP_LLM_TIMEOUT_SECONDS=120
```

`docker compose` 会自动读取项目根的 `.env`。验证是否生效：

```bash
docker compose exec backend python -c "from app.infrastructure.llm import llm_available; print(llm_available())"
```

选模型时注意两点：网关未开通的模型会返回 `product is not activated`；部分大模型响应超过 90 秒会挂住，超时值因此配到 120 秒。

## 5. 单元测试与覆盖率

**「覆盖率 ≥ 60%」指代码覆盖率**（被测试执行到的代码行占比），属于交付完整性要求，与安全测试无关。本项目用 `pytest` + `pytest-cov`，阈值已写死在 `backend/pyproject.toml`：

```toml
[tool.pytest.ini_options]
addopts = "-q --strict-markers"
testpaths = ["tests"]

[tool.coverage.run]
source = ["app"]
omit = ["app/infrastructure/*"]      # 外部网关（LLM、HTTP）不计入，避免用桩测试凑覆盖率

[tool.coverage.report]
fail_under = 60                       # 低于 60% 直接判失败
show_missing = true
skip_covered = true
```

容器内执行：

```bash
docker compose exec backend python -m pytest --cov=app --cov-report=term
```

导出 HTML 报告（评审留档）：

```bash
docker compose exec backend python -m pytest --cov=app --cov-report=html:/tmp/htmlcov
docker compose cp backend:/tmp/htmlcov ./htmlcov
```

测试范围覆盖发现算法与服务、聚类算法与重分配、数据中心接口、抽取与解析、人岗匹配等；38 个文件中 16 个建库跑集成路径，其余为纯函数单测。

## 6. 停止与清理

```bash
docker compose stop                 # 停止容器，保留数据
docker compose down                 # 删除容器与网络，保留数据卷
docker compose down -v              # 连同数据卷一并删除，下次启动重新恢复快照
```

## 7. 排障

| 现象 | 原因与处理 |
| --- | --- |
| `bind: An attempt was made to access a socket…` | Windows 保留端口，见第 4 节 |
| `backend` 反复重启、日志报 `Can't connect to MySQL server on 'mysql'` | 容器挂在了失效网络上，`docker compose up -d --force-recreate backend` |
| 界面能开但数据全空 | `bootstrap` 未跑完，`docker compose logs bootstrap` 查看 |
| 候选文案粗糙、画像是技术词罗列 | LLM 未配置，走了规则降级，见第 4 节 |
| 端口 8000 被占 | 已有另一套栈在跑，`docker ps` 确认后停掉旧的，或改映射端口 |
