#!/usr/bin/env bash
# 生成交付镜像包：交付材料-Docker部署/images/jcg-images.tar.gz
#
# 交付的源码包是裁剪版、不能构建，因此「可执行程序」这一项必须以预构建镜像交付。
# 本脚本产出的包是自足的：三个镜像 + 镜像版 compose，docker load 后即可运行，
# 不需要源码目录、不需要联网拉基础镜像、不挂载任何宿主路径。
#
# 关键点：完整运行库烘进 MySQL 镜像，而不是靠 restore/migrate/bootstrap 三个服务
# 建库——那三个都要挂源码树里的 ./data。烘的方式是 initdb.d，不是 docker commit：
# mysql:8.0 对 /var/lib/mysql 声明了 VOLUME，commit 出来的镜像里那个目录是空的。
#
# 用法：
#   SOURCE_MYSQL=<容器名> bash scripts/build_delivery_images.sh
#
# SOURCE_MYSQL 是要导出数据的运行中 MySQL 容器，默认取演示环境那个。

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$REPO/.runtime/delivery-images"
OUT="$REPO/交付材料-Docker部署/images"
SOURCE_MYSQL="${SOURCE_MYSQL:-job-capability-graph-latest-mysql-1}"
MYSQL_ROOT_PW="${MYSQL_ROOT_PW:-root_password_change_me}"

mkdir -p "$WORK" "$OUT"

echo "==> 从 $SOURCE_MYSQL 导出运行库"
docker exec "$SOURCE_MYSQL" sh -c \
  "MYSQL_PWD=$MYSQL_ROOT_PW mysqldump -uroot --single-transaction --routines --triggers \
   --default-character-set=utf8mb4 job_capability_graph" > "$WORK/dump.sql"

tail -c 100 "$WORK/dump.sql" | grep -q "Dump completed" \
  || { echo "导出不完整，中止"; exit 1; }
echo "    $(wc -l < "$WORK/dump.sql") 行 / $(du -h "$WORK/dump.sql" | cut -f1)"

echo "==> 压缩"
gzip -6 -c "$WORK/dump.sql" > "$WORK/job_capability_graph.sql.gz"

echo "==> 构建镜像"
docker build -f "$WORK/Dockerfile.mysql" -t jcg-mysql:delivery "$WORK"
docker build -t jcg-backend:delivery "$REPO/backend"
docker build -t jcg-frontend:delivery "$REPO/frontend"

echo "==> 导出归档"
docker save jcg-mysql:delivery jcg-backend:delivery jcg-frontend:delivery \
  | gzip -6 > "$OUT/jcg-images.tar.gz"

cd "$OUT"
sha256sum jcg-images.tar.gz > jcg-images.tar.gz.sha256

echo "==> 完成：$OUT/jcg-images.tar.gz（$(du -h jcg-images.tar.gz | cut -f1)）"
echo "    验证：docker compose -f $OUT/docker-compose.yml up -d"
