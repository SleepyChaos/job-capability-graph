#!/usr/bin/env bash
# 生成交付镜像包：交付材料-Docker部署/images/jcg-images.tar.gz
#
# ⚠ 镜像包已不在交付范围内：镜像里是明文 .py，交镜像等于交源码，与源码裁剪的
#   目的冲突。本脚本保留备用，产物默认不提交。当前交付的可执行形态是在线部署
#   与裁剪版源码包（见《交付材料-说明.md》）。
#
# 产出的包是自足的：三个镜像 + 镜像版 compose，docker load 后即可运行，
# 不需要源码目录、不需要联网拉基础镜像、不挂载任何宿主路径。
#
# 关键点：完整运行库烘进 MySQL 镜像，而不是靠 restore/migrate/bootstrap 三个服务
# 建库——那三个都要挂源码树里的 ./data。烘的方式是 initdb.d，不是 docker commit：
# mysql:8.0 对 /var/lib/mysql 声明了 VOLUME，commit 出来的镜像里那个目录是空的。
#
# 用法：
#   bash scripts/build_delivery_images.sh                  # 默认数据卷
#   SOURCE_VOLUME=<卷名> bash scripts/build_delivery_images.sh
#
# 数据源认的是**卷**不是容器。容器会被 Docker Desktop 重启、清理带走（脚本第一版
# 就因为写死容器名，在容器没了之后直接失败），而卷一直在。这里按需在卷上临时起一个
# MySQL 导出，用完即删。

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$REPO/.runtime/delivery-images"
OUT="$REPO/交付材料-Docker部署/images"
SOURCE_VOLUME="${SOURCE_VOLUME:-job-capability-graph-latest_mysql-data}"
MYSQL_ROOT_PW="${MYSQL_ROOT_PW:-root_password_change_me}"
DUMPER="jcg-dump-$$"

mkdir -p "$WORK" "$OUT"

docker volume inspect "$SOURCE_VOLUME" >/dev/null 2>&1 \
  || { echo "找不到数据卷 $SOURCE_VOLUME；用 SOURCE_VOLUME=<卷名> 指定，docker volume ls 可查"; exit 1; }

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

SOURCE_MYSQL="$DUMPER"
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

# 校验和只写文件名，不带路径：载入说明让评审在 images/ 目录里执行
# `sha256sum -c jcg-images.tar.gz.sha256`，带上仓库相对路径会对不上。
cd "$OUT"
sha256sum jcg-images.tar.gz > jcg-images.tar.gz.sha256

echo "==> 完成：$OUT/jcg-images.tar.gz（$(du -h jcg-images.tar.gz | cut -f1)）"
echo "    验证：docker compose -f $OUT/docker-compose.yml up -d"
