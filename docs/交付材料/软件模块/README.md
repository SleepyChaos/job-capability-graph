# 软件模块交付材料

> 对应赛题要求：**源代码（可提供开源链接，私有仓库开放评审权限）、可执行程序（如有）、部署（如 Dockerfile 或容器化部署）说明、单元测试用例（覆盖率 ≥ 60%）。**
> 整理日期：2026-09-03。本目录内的结论均为实测所得，命令可复现。

## 交付物清单

| 赛题要求 | 交付物 | 位置 |
| --- | --- | --- |
| 源代码 | GitHub 仓库（可开放评审权限） | <https://github.com/SleepyChaos/job-capability-graph> · 见 [`01_源代码说明.md`](01_源代码说明.md) |
| 可执行程序 | 三个容器镜像：`backend`（FastAPI）、`frontend`（Nginx 静态站）、`mysql`；`docker compose up` 即可运行 | 构建物由 [`deploy/`](deploy/) 下的 Dockerfile 产出 |
| 部署说明 | Dockerfile、compose 编排、启动步骤、已知坑与排障 | [`02_部署说明.md`](02_部署说明.md) · [`deploy/`](deploy/) |
| 单元测试（覆盖率 ≥ 60%） | **161 项测试全部通过，覆盖率 78.79%** | [`03_单元测试报告.md`](03_单元测试报告.md) · [`单元测试输出.txt`](单元测试输出.txt) |

## 目录结构

```
软件模块/
├── README.md                本文件，交付物清单与对照
├── 01_源代码说明.md          仓库地址、分支、代码规模与目录职责
├── 02_部署说明.md            Docker 启动步骤（完整版见 docs/20）
├── 03_单元测试报告.md        测试范围、覆盖率结论与复现命令
├── 单元测试输出.txt          pytest 原始输出（含逐文件覆盖率），交付证据
├── coverage/                覆盖率 HTML 报告（本地生成，不入库）
└── deploy/                  部署文件副本
    ├── docker-compose.yml
    ├── backend.Dockerfile
    ├── frontend.Dockerfile
    └── frontend.nginx.conf
```

`coverage/` 是 `pytest --cov-report=html` 的产物，随代码变化即失效，因此不入库——
coverage.py 会在该目录内自带 `.gitignore`。归档证据以 `单元测试输出.txt` 为准；
需要 HTML 版时按 [`03_单元测试报告.md`](03_单元测试报告.md) 的命令重新生成，
打包交付时把生成好的 `coverage/` 一并放进压缩包即可。

`deploy/` 下为仓库同名文件的**副本**，便于脱离仓库单独审阅；以仓库内的
`docker-compose.yml`、`backend/Dockerfile`、`frontend/Dockerfile`、`frontend/nginx.conf` 为准。

## 一句话结论

平台已容器化，`docker compose up -d backend frontend` 一条命令拉起数据库、迁移、数据装载与前后端；
后端 161 项单元测试全绿，语句覆盖率 78.79%，高于赛题要求的 60%。
