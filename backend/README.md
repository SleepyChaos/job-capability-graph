# Backend

当前后端采用FastAPI、SQLAlchemy 2和Python 3.11+。第一批实现包含：

- API和数据库健康检查；
- 请求ID；
- JSON结构化日志；
- XLSX只读数据画像；
- 文件资产、导入运行和不可变工作表原始行账本；
- 文件/映射/结构指纹级幂等导入；
- 自动化测试和覆盖率统计。
- Alembic空库迁移与回滚；
- T1–T7、L1–L4及表面词的正式发布；
- 技术体系版本、领域和节点查询API。
- 3718条真实JD、机构别名、来源成员关系和时间质量分级；
- 基于正文哈希的精确重复组与组内证据权重；
- 基于可匹配L4别名、归一到L3标准技术点的确定性抽取与原文证据；
- JD汇总、筛选、列表和详情API。
- 中英文JD职责、硬性要求和加分项的确定性结构化切分；
- 宽泛技术词上下文复核、解析质量分级和聚类特征快照；
- T1–T7分层的120条人工双标候选清单。
- 数据源、单层采集策略、采集运行与请求留痕公共契约；
- 里程碑材料版本、候选事实、原文证据和确定性置信评分；
- 数据审核任务、状态机、前后快照与审核发布闭环。

## 本地初始化

```powershell
cd backend
$env:UV_CACHE_DIR = (Join-Path (Get-Location) '.uv-cache')
uv sync --all-groups
```

复制`.env.example`为`.env`可覆盖数据库等配置。默认使用`backend/.local/dev.db`，该目录不会提交。

初始化或升级数据库：

```powershell
cd backend
.\.venv\Scripts\alembic.exe upgrade head
```

## 启动API

```powershell
cd backend
.\.venv\Scripts\uvicorn.exe app.main:app --reload
```

健康检查：`GET http://127.0.0.1:8000/api/v1/health`。

## 生成XLSX准入画像

```powershell
cd backend
.\.venv\Scripts\python.exe -m tools.profile_source_workbooks `
  --source-root ..\data\source\20260810 `
  --output-dir ..\data\processed\reports\20260810
```

报告不会写入单元格样例值，避免受限人才数据进入公开报告。

## 将工作簿写入本地Raw账本

```powershell
cd backend
.\.venv\Scripts\python.exe -m tools.stage_workbook `
  --file ..\data\source\20260810\core\技术词主数据_20260727.xlsx `
  --storage-key data/source/20260810/core/技术词主数据_20260727.xlsx `
  --importer-code taxonomy_xlsx_v1 `
  --mapping-code technology_taxonomy_20260810 `
  --mapping-version 1.0.0 `
  --classification project_internal `
  --external-key L1技术域=L1编码 `
  --external-key L2技术类=L2编码 `
  --external-key L3技术点=L3编码 `
  --external-key L4技术词=技术词
```

相同文件、导入器、映射版本和结构指纹重复执行时不会产生重复原始行。

只暂存岗位工作表时增加：

```powershell
  --sheet 岗位数据
```

## 发布技术主数据

```powershell
cd backend
.\.venv\Scripts\python.exe -m tools.import_taxonomy `
  --mapping-code technology_taxonomy_20260810 `
  --version-code v1.1 `
  --version-name 具身智能技术词主数据v1.1 `
  --effective-date 2026-07-27 `
  --domain-version v1.1
```

正式发布前会核验固定数量、编码唯一性、L1–L4父链、T1–T7领域和L4重复挂载。查询接口：

- `GET /api/v1/taxonomy/versions`；
- `GET /api/v1/taxonomy/domains`；
- `GET /api/v1/taxonomy/nodes?level=L3&domain_code=T1`。

## 发布真实JD数据底座

先将`具身智能岗位_清洗后_v3(1).xlsx`的`岗位数据`工作表写入Raw账本，再执行：

```powershell
cd backend
.\.venv\Scripts\python.exe -m tools.import_jobs `
  --mapping-code cleaned_job_posting_20260810 `
  --taxonomy-version v1.1 `
  --received-at 2026-08-10T00:00:00
```

导入是幂等的。同一映射再次发布不会重复创建JD。验收报告可用以下命令重建：

```powershell
cd backend
.\.venv\Scripts\python.exe -m tools.validate_job_import `
  --mapping-code cleaned_job_posting_20260810 `
  --output ..\data\processed\reports\20260810\job_import_validation.json
```

JD查询接口：

- `GET /api/v1/jobs/summary`；
- `GET /api/v1/jobs`，支持关键词、来源、等级、学历、时间质量、重复组和技术编码筛选；
- `GET /api/v1/jobs/{job_code}`，返回正文、全部来源、技术要求和命中证据。

## 结构化解析JD并生成聚类输入

```powershell
cd backend
.\.venv\Scripts\python.exe -m tools.parse_jobs `
  --taxonomy-version v1.1 `
  --target-date 2026-08-10
```

解析运行由输入快照、技术体系版本、目标日期和解析器版本共同确定，重复执行不会覆盖或重复生成结果。验收与人工标注候选清单：

```powershell
.\.venv\Scripts\python.exe -m tools.validate_job_parsing `
  --output ..\data\processed\reports\20260810\job_parsing_validation.json

.\.venv\Scripts\python.exe -m tools.build_jd_annotation_batch `
  --sample-count 120 `
  --per-domain-min 10 `
  --output ..\data\evaluation\jd_parsing\annotation_candidates_v1.json
```

解析与聚类准备接口：

- `GET /api/v1/job-parsing/runs`；
- `GET /api/v1/job-parsing/summary`；
- `GET /api/v1/job-parsing/jobs`，支持待审、聚类资格和质量分筛选；
- `GET /api/v1/job-parsing/jobs/{job_code}`，返回职责、技术上下文判定和特征快照；
- `GET /api/v1/job-parsing/ambiguity-rules`。

`annotation_candidates_v1.json`只是待双人标注的候选清单，不能直接作为金标准或准确率依据。

## 数据采集中枢与里程碑审核

采集器通过以下接口登记来源、策略、运行和请求：

- `POST/GET /api/v1/sources`；
- `POST/GET /api/v1/collection-policies`；
- `POST/GET /api/v1/collection-runs`；
- `POST /api/v1/collection-runs/{run_code}/requests`。

结构化里程碑材料提交到 `POST /api/v1/milestones/candidates`。证据引文必须能在正文中精确定位，关联技术编码必须存在于启用的技术主数据。全部里程碑候选进入 `GET /api/v1/reviews/data`，审核操作使用 `POST /api/v1/reviews/data/{task_code}/actions`。

开发阶段审核接口要求 `X-Reviewer-Code`，且该编码必须映射到启用的审核员或管理员。该请求头不是正式认证方案。现有数据包没有可验证里程碑，自动化测试中的 `SYNTH-` 数据只用于集成验收，不会写入正式数据。

## 质量检查

```powershell
cd backend
.\.venv\Scripts\ruff.exe check app tools tests
.\.venv\Scripts\pytest.exe --cov=app --cov=tools --cov-report=term-missing
```
