# 运行数据库快照

本目录包含项目自己的开发基线快照。Docker Compose 默认恢复
`job-capability-graph-mysql-20260901.sql.gz.part-*`。

本目录只保留最新两代 MySQL 快照：当前基线和上一代，供回退与差异比对。更早的快照
从工作区移除，需要时从 Git 历史取回。全量语义复核前的 SQLite 离线参考
`job-capability-graph-runtime.db` 已按此规则退役。

## 当前 MySQL 快照

- 文件：`job-capability-graph-mysql-20260901.sql.gz.part-aa` / `.part-ab` / `.part-ac`
  （合计 82.4 MB，84 张表）
- 数据库结构：Alembic `20260827_0022`
- 技术体系：v1.1–v1.5 五个版本均为 active，最新 v1.5 共 3,167 个节点
  （v1.1 为 2,151 个）；技术别名 12,222 条
- 正式 JD：3,718 条
- 原始文档：17,474 份（3,718 份 JD、13,282 篇 arXiv 论文、474 份里程碑材料）
- LLM 技术复评：803 个条目，来自 4 次复评运行
- 岗位聚类：16 次聚类运行，13,559 个簇版本
- 正式岗位：624 个；岗位版本 792 个（791 approved、1 rejected），待审批 0
- 岗位演变：168 个岗位具备两个及以上版本，787 个演变事件、2,552 个变更项
- 新岗位发现：164 个候选，来自 60 次角色发现运行
- SHA-256（各卷重组后）：
  `15d2a3cccb33a9971d5c0aef01383c59d5614e7fe2850906a2d89817e176e0b4`

快照按 40 MB 分卷存放，卷数随快照增长自动变化（compose 用通配符重组，不需要改配置）。
GitHub 对**单个文件**超过 50 MB 会发出大文件警告，整份 gzip 会触发它；分卷后每卷都在
阈值以下。恢复时先用 `cat` 按后缀顺序
重组再解压，`split`/`cat` 是逐字节还原，重组结果的 SHA-256 与下方记录一致：

```
cat job-capability-graph-mysql-20260901.sql.gz.part-* | gunzip -c | mysql ...
```

分卷只是绕开单文件阈值，并不减少仓库体积。若要真正抑制 `.git` 增长，需要改用
Git LFS 存放本目录的快照。

快照由当前 Docker MySQL 使用 `mysqldump --single-transaction` 导出并 gzip 压缩。
它不包含 `.env` 或 DeepSeek API Key，也不包含候选人画像与简历原文——人才模块的
12 张候选人相关表在导出前已清空，快照恢复后人才画像列表为空态。

arXiv 论文语料随本快照分发。`data/upstream/` 按体积原因不入库，若只从核心 XLSX
重建（`RESTORE_RUNTIME_SNAPSHOT=0`），文献检索页会是空的——需要另行取得语料后运行
`python -m tools.import_arxiv_documents`。

## 上一代 MySQL 快照

- 文件：`job-capability-graph-mysql-20260812.sql.gz`
- 数据库结构：Alembic `20260812_0013`
- 技术体系：v1.1，2,151 个节点
- 正式 JD：3,718 条
- DeepSeek 审计条目：803 条（含三轮小样本和一轮 735 条全量）
- 技术候选：7,591 条，其中 7,057 条 accepted、534 条 needs_review
- 最新岗位聚类：2,102 个
- 正式岗位/已审批版本：116/116，待审批 0
- SHA-256：`fbd855cf106f0ec915e2e1ca50b52257744419a95df13dfd46af0b16c1f0b260`

所有快照都使用项目设计的数据库结构和导入服务，不执行数据包目录中的废弃 SQL。设置
`RESTORE_RUNTIME_SNAPSHOT=0` 可跳过 MySQL 快照，改由 `bootstrap` 从
`data/source/20260810/core` 的核心 XLSX 幂等重建。

数据包中的受限人才/高校工作簿和派生 XLSX 没有作为本快照的正式事实导入。
