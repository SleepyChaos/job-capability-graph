# 运行数据库快照

本目录包含项目自己的开发基线快照。Docker Compose 默认恢复 `job-capability-graph-mysql-20260812.sql.gz`；`job-capability-graph-runtime.db` 保留为全量语义复核前的 SQLite 离线参考。

## 当前 MySQL 快照

- 文件：`job-capability-graph-mysql-20260812.sql.gz`
- 数据库结构：Alembic `20260812_0013`
- 技术体系：v1.1，2,151 个节点
- 正式 JD：3,718 条
- DeepSeek 审计条目：803 条（含三轮小样本和一轮 735 条全量）
- 技术候选：7,591 条，其中 7,057 条 accepted、534 条 needs_review
- 最新岗位聚类：2,102 个
- 正式岗位/已审批版本：116/116，待审批 0
- SHA-256：`fbd855cf106f0ec915e2e1ca50b52257744419a95df13dfd46af0b16c1f0b260`

快照由当前 Docker MySQL 使用 `mysqldump --single-transaction` 导出并 gzip 压缩。它不包含 `.env` 或 DeepSeek API Key。

## 历史 SQLite 快照

- 数据库结构：Alembic `20260812_0012`
- 技术体系：v1.1，2,151 个节点
- 正式 JD：3,718 条
- 岗位聚类：2,096 个
- 岗位版本：113 个，已通过开发基线审核
- SHA-256：`414f5931938654e3704044c1fdc4dd3d13e7224722473b6dc8596e9b0a1671ec`

所有快照都使用项目设计的数据库结构和导入服务，不执行数据包目录中的废弃 SQL。设置 `RESTORE_RUNTIME_SNAPSHOT=0` 可跳过 MySQL 快照，改由 `bootstrap` 从 `data/source/20260810/core` 的核心 XLSX 幂等重建。

数据包中的受限人才/高校工作簿和派生 XLSX 没有作为本快照的正式事实导入。
