#!/usr/bin/env bash
# 导出运行库快照，供裁剪源码包随包分发。
#
# 裁剪包里 backend/tools/ 全是桩，原来 compose 靠 bootstrap 从核心 XLSX 建库的
# 那条路断了。要让评审 `docker compose up` 就能看到真实数据，只能随包给一份
# 已审计的库快照。快照是数据，不含任何源码。
#
# 数据源认**卷**不认容器：容器会被 Docker Desktop 重启、清理带走，卷一直在。
# 这里在卷上临时起一个 MySQL 导出，用完即删。
#
# 用法：
#   bash scripts/dump_runtime_db.sh
#   SOURCE_VOLUME=<卷名> bash scripts/dump_runtime_db.sh

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$REPO/.runtime/delivery-images"
SOURCE_VOLUME="${SOURCE_VOLUME:-job-capability-graph-latest_mysql-data}"
MYSQL_ROOT_PW="${MYSQL_ROOT_PW:-root_password_change_me}"
DUMPER="jcg-dump-$$"

mkdir -p "$OUT"

docker volume inspect "$SOURCE_VOLUME" >/dev/null 2>&1 \
  || { echo "找不到数据卷 $SOURCE_VOLUME；docker volume ls 可查，用 SOURCE_VOLUME= 指定"; exit 1; }

cleanup() { docker rm -f "$DUMPER" >/dev/null 2>&1 || true; }
trap cleanup EXIT

echo "==> 在卷 $SOURCE_VOLUME 上临时起 MySQL"
docker run -d --name "$DUMPER" \
  -e MYSQL_ROOT_PASSWORD="$MYSQL_ROOT_PW" \
  -v "$SOURCE_VOLUME:/var/lib/mysql" \
  mysql:8.0 >/dev/null

for i in $(seq 1 60); do
  docker exec "$DUMPER" mysqladmin ping -h 127.0.0.1 -uroot -p"$MYSQL_ROOT_PW" >/dev/null 2>&1 && break
  [ "$i" = 60 ] && { echo "MySQL 未能在 5 分钟内就绪"; exit 1; }
  sleep 5
done

echo "==> 导出"
docker exec "$DUMPER" sh -c \
  "MYSQL_PWD=$MYSQL_ROOT_PW mysqldump -uroot --single-transaction --routines --triggers \
   --default-character-set=utf8mb4 job_capability_graph" > "$OUT/dump.sql"

tail -c 100 "$OUT/dump.sql" | grep -q "Dump completed" \
  || { echo "导出不完整，中止"; exit 1; }

tables="$(grep -c '^CREATE TABLE' "$OUT/dump.sql")"
echo "    $tables 张表 / $(du -h "$OUT/dump.sql" | cut -f1)"

gzip -6 -c "$OUT/dump.sql" > "$OUT/job_capability_graph.sql.gz"
rm -f "$OUT/dump.sql"

echo "==> 完成：$OUT/job_capability_graph.sql.gz（$(du -h "$OUT/job_capability_graph.sql.gz" | cut -f1)）"
echo "    接着跑 python scripts/build_redacted_source_package.py 把它打进裁剪包"
