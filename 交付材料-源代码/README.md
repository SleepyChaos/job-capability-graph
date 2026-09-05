# 交付材料 · 源代码（裁剪版，可运行）

对应赛题「软件模块」交付项：**源代码**与**可执行程序**。测试材料在 `交付材料-单元测试/`，
部署说明在 `交付材料-Docker部署/`。

## ⚠️ 本包是裁剪版

4 组核心算法模块（93 个文件、24,481 行）的实现已移除，保留目录、文件名、公开接口签名、
模块级常量与文档字符串。**裁剪范围、原因与影响见根目录 [`源码裁剪说明.md`](../源码裁剪说明.md)——审阅前请先读那份。**

**但本包可以运行。** 被裁的是计算与写入逻辑；数据浏览、图谱、画像查看等读取链路完整可用。
调用到被裁实现的端点返回 **HTTP 501** 并指向在线部署，不是崩溃。

## 两步启动

```bash
cd src
```

```bash
docker compose up -d --build
```

**首次启动约需 6 分钟**：MySQL 导入随包的运行库快照（约 4 分钟），前后端镜像构建（约 2 分钟）。
之后重启即时可用。

| 入口 | 地址 |
| --- | --- |
| 平台 | <http://localhost:8080> |
| 接口文档 | <http://localhost:8000/docs> |
| 健康检查 | <http://localhost:8000/api/v1/health> |

看导入进度：`docker compose logs -f mysql`，出现 `ready for connections` 即完成。

## 实测结论

在干净卷上从本包 `docker compose up --build` 全量验证：

```
mysql / backend / frontend    三个容器全部 healthy
后端健康检查                   {"status":"ok","database":"ok"}
无参 GET 端点                  37 条中 36 条 200（另 1 条为需登录的 /auth/me → 401）
前端                          index.html 200、/api 代理 200
图谱产物 gzip                  39,528,020 → 3,909,713 字节
被裁端点                       run_discovery / auto_candidate_portrait → 501
```

## 能做什么 / 不能做什么

| | 状态 |
| --- | --- |
| 岗位画像图谱、产业图谱、技术图谱浏览 | ✅ 完整可用，真实数据 |
| 新岗位发现候选卡、五维画像查看 | ✅ 完整可用 |
| 岗位聚类结果、技术词表、数据采集治理 | ✅ 完整可用 |
| **点「运行自动预测」生成候选** | ⛔ 501 → 在线部署 |
| **点「生成五维画像」** | ⛔ 501 → 在线部署 |
| **重新执行岗位聚类** | ⛔ 501 → 在线部署 |
| 从核心 XLSX 重建数据（离线管线） | ⛔ `backend/tools/` 全为桩 |

完整功能请访问在线部署：<http://122.51.220.41:8080/>

501 响应体长这样，评审能一眼看出是有意裁剪而非故障：

```json
{
  "error": "redacted_in_delivery",
  "message": "本功能的实现未包含在交付裁剪版源码包中。",
  "detail": "app.modules.discovery.service.run_discovery",
  "online_deployment": "http://122.51.220.41:8080/",
  "reference": "源码裁剪说明.md"
}
```

## 内容

| 路径 | 说明 |
| --- | --- |
| [`src/`](src/) | 裁剪后的源码树 |
| [`裁剪清单.json`](裁剪清单.json) | 逐文件裁剪清单（路径 + 原始行数），机器可读 |

```
src/
├── docker-compose.yml    裁剪包专用编排（无 bootstrap，见下）
├── db/                   运行库快照 84 MB，首启自动导入
├── backend/
│   ├── app/api/          FastAPI 路由层            保留
│   │   modules/          领域模块                  部分裁剪
│   │   core/ db/         配置、会话与引擎          保留
│   │   core/redacted.py  501 占位异常（构建时注入，非原始代码）
│   ├── migrations/       Alembic 迁移              保留
│   ├── tools/            离线管线                  已裁剪（82 个文件）
│   └── tests/            单元测试                  保留（38 个文件）
└── frontend/
    ├── src/              页面、图谱组件、接口客户端  保留
    └── public/           图谱静态产物              保留（运行所需）
```

## 规模

| 项 | 文件数 | 源码行数 |
| --- | ---: | ---: |
| 保留 | 233 | 49,878 |
| 裁剪 | 93 | 24,481 |

行数只统计源码（`.py`/`.ts`/`.md` 等），不含图谱 JSON 等数据产物。包体 131 MB，
其中运行库快照 84 MB、图谱产物 41 MB。

## 与仓库版 compose 的区别

`src/docker-compose.yml` **不是**仓库根目录那份的副本，必须不同：

| 服务 | 裁剪包为什么没有 |
| --- | --- |
| `bootstrap` | 调用 `backend/tools/` 从核心 XLSX 重建数据，而 tools 在本包中全为桩，必然失败 |
| `restore` / `migrate` | 快照已是 Alembic head 结构，MySQL 官方 entrypoint 自动导入 `db/`，无需额外服务 |

`backend` 与 `frontend` 仍是 `build:`，从本包源码构建——这是源码交付物，评审应当能亲自构建。

## 复现

```bash
bash scripts/dump_runtime_db.sh                     # 导出运行库快照
python scripts/build_redacted_source_package.py     # 生成裁剪包
```
