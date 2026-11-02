# 具身智能岗位—能力图谱

本项目从真实 JD 和受治理的技术词体系中抽取岗位能力，完成岗位聚类、能力图谱、岗位演化和人岗匹配。当前分支包含 Canvas/Web Worker 大规模关系图，以及 DeepSeek 闭集语义复核流程。

## 项目状态与阅读入口

这是具身智能领域的岗位治理、能力图谱与新岗位发现研究项目，适合本地演示和方法验证。真实市场演化结论需要真实时间窗与独立评测；部分历史实验使用了合成观测窗，不应直接解读为市场趋势。具体版本与边界见 [MVP 现状](docs/01-MVP现状与边界.md) 和 [新岗位发现与动态更新设计](docs/11-新岗位发现与岗位动态更新模块设计.md)，阅读时保留文档各自的状态日期。

- 第一次体验：使用下方 Docker Compose 入口，随后查看前端图谱与后端健康检查。
- 理解系统：[文档导航](docs/README.md)、[系统架构与数据流](docs/02-系统架构与数据流.md)。
- 复现实验：记录代码版本、数据版本和模型配置；运行快照与前端图谱文件可能属于不同数据口径。
- 数据依赖：[仓库数据说明](DATA.md)、[运行快照清单](data/runtime/README.md)。首次克隆会取得较大的数据文件。

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

后端默认从 `data/runtime/job-capability-graph-mysql-20260901.sql.gz.part-*` 分卷恢复数据库，然后执行迁移与初始化。完整分卷必须保留；单独删除某一卷会使首次恢复失败。快照版本、内容与重组校验值以 [运行快照清单](data/runtime/README.md) 为准。

旧的 `20260812` 快照保留作回退参考，不是当前 Compose 的默认入口。前端 v4 文件、快照恢复结果和后续迁移后的数据库不能按同一组统计数字解释。

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
