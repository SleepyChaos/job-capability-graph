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

## 质量检查

```powershell
cd backend
.\.venv\Scripts\ruff.exe check app tools tests
.\.venv\Scripts\pytest.exe --cov=app --cov=tools --cov-report=term-missing
```
