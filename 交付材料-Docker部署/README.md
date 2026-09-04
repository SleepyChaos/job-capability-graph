# 交付材料 · Docker 部署

本目录只放**怎么把系统跑起来**所需的材料。测试相关材料在同级的 `交付材料-单元测试/`。

## 内容

| 文件 | 说明 |
| --- | --- |
| [`Docker部署说明.md`](Docker部署说明.md) | 主文档：环境要求、一键启动、compose 编排、两个已知坑、停止清理、排障表 |
| [`源代码说明.md`](源代码说明.md) | 仓库地址、分支、代码规模、目录职责与技术栈——评审拿到代码后先看这份 |
| [`deploy/`](deploy/) | 部署文件副本：`docker-compose.yml`、后端与前端 Dockerfile、nginx 配置 |

`deploy/` 下是仓库同名文件的副本，便于脱离仓库单独审阅；以仓库内的
`docker-compose.yml`、`backend/Dockerfile`、`frontend/Dockerfile`、`frontend/nginx.conf` 为准。

## 最短路径

```bash
git clone https://github.com/SleepyChaos/job-capability-graph.git
cd job-capability-graph
docker compose up -d backend frontend
```

一次 `up` 会依次完成：起 MySQL → 恢复已审计快照 → Alembic 迁移 → 从核心 XLSX 装载并跑解析/聚类 → 起后端与前端。

启动后：平台 <http://localhost:8080> · 接口文档 <http://localhost:8000/docs> · 健康检查 <http://localhost:8000/api/v1/health>

## 两个必看的坑

1. **Windows 保留端口**：Docker Desktop 重启后 `8043–8242`（含 8080）可能被系统划走，容器绑不上端口。查 `netsh int ipv4 show excludedportrange protocol=tcp`，避开该段改映射。
2. **LLM 网关默认不开**：候选表达层与五维画像生成需要 LLM，未配置时降级为规则输出——功能不报错，但文案质量明显下降。密钥只从未入库的 `.env` 注入。

两者的细节与处理办法都在 [`Docker部署说明.md`](Docker部署说明.md)。
