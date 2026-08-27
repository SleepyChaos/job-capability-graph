# 具身智能岗位—能力图谱

本项目从真实 JD 和受治理的技术词体系中抽取岗位能力，完成岗位聚类、能力图谱、岗位演化和人岗匹配。当前分支包含 Canvas/Web Worker 大规模关系图，以及 DeepSeek 闭集语义复核流程。

## 一键启动

### Windows 本地开发（推荐用于当前工作区）

仓库根目录提供统一启动入口，固定使用前端 `8080`、后端 `8000`。脚本会复用已健康的服务、拒绝占用冲突端口，并在 `.runtime` 保存进程与日志。

```powershell
powershell -ExecutionPolicy Bypass -File .\start-local.ps1
```

停止由该脚本启动的服务：

```powershell
powershell -ExecutionPolicy Bypass -File .\stop-local.ps1
```

开发服务器与 `vite preview` 均代理 `/api` 到后端，避免预览模式打开页面后筛选请求失效。

### Docker Compose

要求：Docker Desktop 或兼容的 Docker Engine，支持 `docker compose`。

```bash
git clone https://github.com/SleepyChaos/job-capability-graph.git
cd job-capability-graph
docker compose up --build -d
```

首次启动会按以下顺序运行：

```text
MySQL → 恢复已审计数据快照 → Alembic 迁移 → 幂等数据补全 → 后端 → 前端
```

启动后访问：

- 前端：<http://127.0.0.1:8080>
- 后端健康检查：<http://127.0.0.1:8000/api/v1/health>
- OpenAPI：<http://127.0.0.1:8000/docs>

查看运行状态和日志：

```bash
docker compose ps
docker compose logs -f backend frontend
```

停止服务但保留 MySQL 数据：

```bash
docker compose down
```

## 当前数据版本

岗位生态图谱已升级为 v4 企业增强候选版，数据源位于 `data/source/20260826/core/岗位信息v4_企业增强分析.xlsx`：

- 岗位事实：4,655 条；
- 企业库：633 条企业实体；
- 已关联企业属性的岗位：4,472 条（96.1%），覆盖 102 个企业实体；
- 待核验或待补全：183 条，未强行赋予产业链、地区或融资属性；
- 岗位图谱：6 个职业方向、17 个职业种类、42 个可解释候选岗位簇；
- 企业图谱：岗位连接企业，再连接产业链层级、细分领域、融资轮次、所属地区和总部城市。

前端“岗位生态图谱”可在“岗位层级”和“企业视角”之间切换。候选岗位簇仍需 Embedding + HDBSCAN 稳定性检验和专家校准后才能作为正式发布版本。

以下 MySQL 快照仍是后端默认运行库基线，不与上述 v4 文件口径混用：

仓库内的 `data/runtime/job-capability-graph-mysql-20260812.sql.gz` 是默认恢复快照：

- Alembic：`20260812_0013`
- 技术节点：2,151
- 正式 JD：3,718
- 技术候选：7,591，其中 7,057 已接受、534 保留待审核
- DeepSeek 全量复核：735 条，201 条高置信结果回写，影响 136 个岗位
- 最新岗位聚类：2,102
- 正式岗位及已审批版本：116，当前待审批 0
- 快照 SHA-256：`fbd855cf106f0ec915e2e1ca50b52257744419a95df13dfd46af0b16c1f0b260`

快照不包含 `.env` 或 DeepSeek API Key。数据来源仍是仓库内核心 XLSX，未使用数据包中的废弃 SQL 设计。

## DeepSeek 配置与复核

复制根目录环境变量模板或创建不入库的 `.env`：

```dotenv
APP_LLM_API_KEY=your-key
APP_LLM_BASE_URL=https://api.deepseek.com/v1
APP_LLM_MODEL=deepseek-v4-flash
```

默认调用模型为 `deepseek-v4-flash`。旧变量名 `OPENAI_API_KEY`、`OPENAI_BASE_URL`、`LLM_MODEL` 也兼容。先做不回写测试：

```bash
docker compose exec backend python -m tools.reassess_technologies_llm \
  --parse-run-code jdparse_8ad8184577692c219c983899 \
  --limit 24 --batch-size 12 --no-apply
```

模型只能对现有技术编码做 `accepted/rejected/uncertain` 闭集判断；证据引文必须逐字存在于 JD 上下文。只有通过校验且达到阈值的接受项会更新特征，模型不能发明新技术编码。

## 从原始 XLSX 重建

若不使用 GitHub 中的运行快照，可在一个新的空卷上执行：

```bash
RESTORE_RUNTIME_SNAPSHOT=0 docker compose up --build -d
```

该流程只使用项目 Alembic 结构和 `data/source/20260810/core` 中的核心 XLSX。清空已有卷会删除本地 MySQL 数据，具体操作和限制见 [测试、部署与运维](docs/04-测试部署与运维.md)。

## 开发验证

```bash
cd backend
.venv/bin/ruff check app tests tools
.venv/bin/pytest

cd ../frontend
pnpm build
```

项目状态、架构、数据口径和后续任务统一从 [`docs/README.md`](docs/README.md) 进入；后端开发命令见 [`backend/README.md`](backend/README.md)。
