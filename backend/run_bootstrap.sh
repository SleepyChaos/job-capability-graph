#!/bin/bash
set -e
cd /c/Users/10741/WorkBuddy/2026-08-14-11-44-53/job-capability-graph/backend
PY=.venv/Scripts/python.exe
DATA=C:/Users/10741/WorkBuddy/2026-08-14-11-44-53/job-capability-graph/data/source/20260810/core

# [1/8] seed_reviewers (已成功执行过，跳过以避免 unique 冲突)
# $PY -m tools.seed_reviewers

echo "[2/8] stage_workbook (技术词主数据)"
$PY -m tools.stage_workbook \
  --file "$DATA/技术词主数据_20260727.xlsx" \
  --storage-key 'data/source/20260810/core/技术词主数据_20260727.xlsx' \
  --importer-code taxonomy_xlsx_v1 \
  --mapping-code technology_taxonomy_20260810 \
  --mapping-version 1.0.0 \
  --classification project_internal \
  --external-key 'L1技术域=L1编码' \
  --external-key 'L2技术类=L2编码' \
  --external-key 'L3技术点=L3编码' \
  --external-key 'L4技术词=技术词'

echo "[3/8] import_taxonomy"
$PY -m tools.import_taxonomy \
  --mapping-code technology_taxonomy_20260810 \
  --version-code v1.1 \
  --version-name '具身智能技术词主数据v1.1' \
  --effective-date 2026-07-27 \
  --domain-version v1.1

echo "[4/8] stage_workbook (岗位数据)"
$PY -m tools.stage_workbook \
  --file "$DATA/具身智能岗位_清洗后_v3(1).xlsx" \
  --storage-key 'data/source/20260810/core/具身智能岗位_清洗后_v3(1).xlsx' \
  --importer-code cleaned_job_xlsx_v1 \
  --mapping-code cleaned_job_posting_20260810 \
  --mapping-version 1.0.0 \
  --classification project_internal \
  --external-key '岗位数据=occ_id' \
  --sheet '岗位数据'

echo "[5/8] import_jobs"
$PY -m tools.import_jobs \
  --mapping-code cleaned_job_posting_20260810 \
  --taxonomy-version v1.1 \
  --received-at 2026-08-10T00:00:00

echo "[6/8] parse_jobs"
parse_output=$($PY -m tools.parse_jobs --taxonomy-version v1.1 --target-date 2026-08-10)
parse_run_code=$(printf '%s' "$parse_output" | $PY -c 'import json,sys; print(json.load(sys.stdin)["run_code"])')
echo "PARSE_RUN_CODE=$parse_run_code"

echo "[7/8] cluster_jobs"
$PY -m tools.cluster_jobs --parse-run-code "$parse_run_code" \
  --assign-threshold 0.36 \
  --grey-threshold 0.24 \
  --top-k 3 \
  --max-cluster-size 120

echo "[8/8] approve_all_role_reviews"
$PY -m tools.approve_all_role_reviews --reviewer-code reviewer-demo

echo "BOOTSTRAP_DONE"
