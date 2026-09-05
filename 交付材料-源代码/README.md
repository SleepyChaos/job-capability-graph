# 交付材料 · 源代码

具身智能岗位能力图谱平台源码。部署说明在 `交付材料-Docker部署/`，测试材料在
`交付材料-单元测试/`。

## 启动

```bash
cd src
```

```bash
docker compose up -d --build
```

**首次启动约 6 分钟**：MySQL 导入随包的运行库快照（约 4 分钟）、前后端镜像构建（约 2 分钟）。
之后重启即时可用。看导入进度：`docker compose logs -f mysql`，出现 `ready for connections`
即完成。

| 入口 | 地址 |
| --- | --- |
| 平台 | <http://localhost:8080> |
| 接口文档 | <http://localhost:8000/docs> |
| 健康检查 | <http://localhost:8000/api/v1/health> |

实测（干净卷）：三个容器全部 healthy，健康检查返回 `{"status":"ok","database":"ok"}`，
37 个无参 GET 端点中 36 个返回 200（另一个为需登录的 `/auth/me`），前端与 `/api` 代理均正常。

## 内容

```
src/
├── docker-compose.yml    容器编排
├── db/                   运行库快照 84 MB，首启自动导入
├── backend/
│   ├── app/api/          FastAPI 路由层
│   │   modules/          领域模块
│   │   core/ db/         配置、会话与引擎
│   ├── migrations/       Alembic 迁移
│   ├── tools/            离线管线
│   └── tests/            单元测试（38 个文件）
└── frontend/
    ├── src/              页面、图谱组件、接口客户端
    └── public/           图谱静态产物
```

技术栈：FastAPI + SQLAlchemy 2 + Alembic + MySQL 8.0；React 19 + TypeScript + Vite +
AntV G6；Nginx 静态站 + `/api` 反向代理。

包体 131 MB，其中运行库快照 84 MB、图谱产物 41 MB，源码本身约 3 MB。

## 说明

新岗位发现推演、岗位聚类与结构化抽取是本作品的核心方法，这几个模块（93 个文件，
清单见 [`裁剪清单.json`](裁剪清单.json)）仅保留公开接口签名与文档字符串，未包含具体实现；
其余代码完整提交。

数据浏览、岗位画像图谱、产业图谱、技术图谱、候选数据卡、五维画像查看、聚类结果与技术
词表均正常可用，数据真实。调用到未包含实现的操作——运行自动预测、生成五维画像、重跑
岗位聚类——返回 HTTP 501：

```json
{
  "error": "not_implemented_in_this_build",
  "message": "本交付版本未包含该功能的实现，完整功能见在线部署。",
  "detail": "app.modules.discovery.service.run_discovery",
  "online_deployment": "http://122.51.220.41:8080/"
}
```

完整功能请访问在线部署 <http://122.51.220.41:8080/>。完整实现保留在私有仓库
<https://github.com/SleepyChaos/job-capability-graph>，可按赛事要求向评审开放访问权限。

## 容器编排

`src/docker-compose.yml` 三个服务：`mysql`（导入 `db/` 下的快照）、`backend`
（`build: ./backend`）、`frontend`（`build: ./frontend`）。

快照已是 Alembic head 结构，无需额外的迁移与装载服务；`backend/tools/` 下的离线管线用于
从核心 XLSX 重建数据，本版本未包含其实现。
