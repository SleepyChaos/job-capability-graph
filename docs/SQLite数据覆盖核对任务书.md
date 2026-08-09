# main分支 SQLite 数据覆盖核对任务书

> 核对目标：判断 main 分支 SQLite 中的**真实数据及字段**能否覆盖新系统目标数据库所需输入
> 目标结构：`database/target_schema_v1_mysql8.sql`
> 注意：不得以旧 SQLite 是否存在运行表、审核表和匹配结果表来判断原始数据是否完整

## 1. 交给核对者的任务

请只读检查 main 分支及其 SQLite 数据库，不修改数据。把 SQLite 的表、字段和真实记录映射到目标结构，并回答：

1. 哪些目标字段可以直接映射；
2. 哪些字段可以通过清洗、拆分、聚合或规则计算得到；
3. 哪些字段完全没有原始数据；
4. 哪些表属于新系统派生/运行数据，本来就不应要求 SQLite 已存在；
5. 现有记录量、时间范围、空值、重复和来源覆盖是否足够支持算法；
6. 当前 SQLite 是否足以运行一版 TETG-EJD v1；
7. 还需要补采哪些数据，以及补采优先级。

## 2. 数据覆盖状态枚举

每个目标表和字段必须标为以下一种：

| 状态 | 含义 |
| --- | --- |
| `DIRECT` | SQLite 中已有语义一致的字段，可直接迁移 |
| `TRANSFORM` | 有原始信息，但需清洗、拆分、枚举转换或去重 |
| `DERIVABLE` | 能由现有数据和算法重新计算，不是原始数据缺失 |
| `SAMPLE_ONLY` | 只有少量样本，无法支撑正式统计 |
| `ABSENT` | 没有原始数据，也无法可靠推导 |
| `NOT_EXPECTED` | 新系统运行后才产生，不要求旧库已有 |
| `UNCERTAIN` | 字段含义或数据质量无法确定，需要人工确认 |

不得把空表或只有演示记录的表标为 `DIRECT`。

## 3. 核对范围分级

目标 SQL 中每张表的注释包含分类：

- `[A]`：基础真实数据，是本次核对重点；
- `[B]`：由基础数据和算法计算，可标记 `DERIVABLE`；
- `[C]`：运行、审核、画像、匹配或评测后产生，可标记 `NOT_EXPECTED`；
- `[A/B]`、`[A/C]`：既可能迁移旧数据，也允许在新系统中补充产生，需要逐字段判断。

## 4. 必查基础数据域

### 4.1 技术主数据——权重20%

至少核对：

```text
md_technology_taxonomy_version
md_technology_node
md_technology_alias
md_technology_domain
rel_technology_node_domain
md_capability
rel_capability_technology
rel_technology_relation
biz_technology_term_candidate
```

关键问题：

- 是否真的具有 L1、L2、L3、L4 四层，而不只是编码文本；
- 父子关系是否完整、是否存在孤儿节点或循环；
- 技术编码在不同版本是否稳定；
- 是否有标准名、定义和别名；
- T1–T7 是否为独立字段/关系，而不是把7个L1误当成T1–T7；
- 技术点是否能映射到广义能力；
- 是否有前置、演化、应用等技术关系；
- 旧文档中的技术编码如 `T1.02` 到底是 L 编码还是 T 领域编码，必须确认语义。

### 4.2 真实JD——权重30%

至少核对：

```text
biz_job_posting
biz_job_responsibility
biz_job_requirement
rel_job_scenario
rel_job_fact_evidence
md_organization
md_organization_alias
md_data_source
```

关键字段：

```text
岗位标题
企业名称和可去重企业ID
JD原文
真实来源URL/来源平台
来源岗位ID
发布日期和采集时间
在聘/下架状态
地点、薪资、学历、经验、岗位级别
职责列表
必需/加分/前沿技能
原始技术词与标准技术ID
应用场景
字段对应的原文片段
```

必须统计：

- 总 JD 数、非空 JD 数和去重后 JD 数；
- 独立企业数、独立来源数；
- 有发布日期的比例和最早/最晚日期；
- 有职责、技能、来源 URL 的比例；
- 完全相同 JD、同公司重复岗位和跨平台转载比例；
- 是否存在至少100条可用于固定测试集的高质量 JD。

### 4.3 技术里程碑——权重15%

至少核对：

```text
biz_milestone_event
rel_milestone_technology
rel_milestone_scenario
rel_milestone_evidence
```

关键字段：

```text
事件名称和描述
事件日期/年份
事件类型
来源URL或来源文档
相关机构
相关标准技术ID
相关度
应用场景
候选/已验证状态
原文证据
```

旧算法需要按目标日期截断，因此只有年份而没有具体日期时要单独标注。还要检查是否能区分论文、突破、开源、产品、平台、规模部署和标准政策。

### 4.4 来源、原文和证据——权重10%

至少核对：

```text
md_data_source
raw_source_document
raw_source_document_version
raw_file_asset
biz_evidence_span
```

关键问题：

- 每条JD、里程碑和技术词能否回到真实来源；
- 是否保存原始链接、原始正文和采集时间；
- 是否有内容哈希或足够字段生成稳定哈希；
- 是否能识别同一文档的不同版本；
- 是否能定位到职责/要求/场景原文片段；
- 是否能区分独立来源和转载链。

如果只有清洗后的结构化表而没有原文及来源，算法仍可运行，但证据链、幻觉防控和官方可验证性应判为重大缺口。

### 4.5 岗位基线和聚类——权重10%

至少核对：

```text
biz_job_clustering_run
biz_job_cluster_version
rel_job_cluster_member
rel_job_cluster_lineage
biz_job_role
md_job_role_alias
biz_job_role_version
rel_job_role_version_requirement
```

旧 SQLite 不必已有完整版本和谱系，可以标记 `DERIVABLE`。但必须判断是否具备计算它们的基础：

- 足够完整的 JD 标题、职责、技能、场景和级别；
- 已有职业方向/岗位类型及其定义；
- JD 到已有岗位的关系；
- 岗位别名或同义名称；
- 已有岗位技能需求基线。

如果只保存岗位名而没有职责与技能，不能可靠完成聚类和“已有岗位覆盖度”。

### 4.6 场景、能力和任务语义——权重10%

至少检查：

- 是否有标准应用场景；
- 是否有职责/任务文本；
- 是否有技术之外的任务能力或通用能力；
- 是否有技能熟练度、必需/加分标签；
- 是否能从 JD 中提取动作、对象和产出；
- 是否有企业产品、应用落地或其他产业任务材料。

### 4.7 可选支持数据——权重5%

政策、论文、专利、标准、产品、融资和高校数据不是第一版闭环的必需项。请判断它们能否补充：

- 技术里程碑；
- 技术成熟度；
- 应用落地证据；
- 机构和场景关系。

不要因为可选产业数据很丰富，就掩盖 JD、时间、来源或技术映射的缺失。

## 5. TETG-EJD v1 最小可运行字段

下面字段若缺失，必须单独列为算法阻断项。

### 技术

```text
technology_id/code
standard_name
level(L1-L4)
parent_id
definition
aliases
T1-T7 domain memberships
```

### 里程碑

```text
milestone_id
name
description
event_date/year
event_type
source/source_url
technology links
verification status or enough evidence to review
```

### JD

```text
job_id
job_title
organization/company
jd_text
source_url/source
published_at or collected_at
technology terms/links
responsibility text
required/bonus labels if available
```

### 既有岗位基线

```text
role_id/name/aliases
role responsibility definition
role requirements
JD-to-role or enough fields to recompute clustering
```

## 6. 不要求 SQLite 预先覆盖的内容

以下内容正常情况下标为 `NOT_EXPECTED` 或 `DERIVABLE`，不能算作原始数据缺失：

- 采集运行、抽取运行和审核任务；
- 文档质量分和重复簇；
- 岗位聚类运行、成员分数和谱系；
- 岗位周期指标、能力重要度和45天热力聚合；
- 技术成熟度快照和每条里程碑贡献；
- 产业任务缺口、任务社区和候选岗位评分；
- LLM岗位定义和标准JD；
- 求职者画像版本、问答、匹配和学习路径；
- 基准评测运行和指标。

但必须检查产生这些派生结果所需的基础字段是否存在。

## 7. SQLite只读检查建议

先定位所有数据库文件，再对每个文件执行：

```sql
SELECT name, type, sql
FROM sqlite_master
WHERE type IN ('table','view')
ORDER BY type, name;
```

对每张候选表执行：

```sql
PRAGMA table_info('<table_name>');
PRAGMA foreign_key_list('<table_name>');
PRAGMA index_list('<table_name>');
SELECT COUNT(*) FROM <table_name>;
```

对关键字段统计：

```sql
SELECT
  COUNT(*) AS total_count,
  SUM(CASE WHEN <field> IS NULL OR TRIM(CAST(<field> AS TEXT)) = '' THEN 1 ELSE 0 END) AS empty_count,
  COUNT(DISTINCT <field>) AS distinct_count
FROM <table_name>;
```

对时间和企业覆盖统计最小值、最大值、独立企业数，并抽取若干真实样本核对字段语义。不要只查看DDL。

## 8. 必须提交的结果文件

### 8.1 数据库清单

| SQLite文件 | 表数 | 总记录量 | 主要数据域 | 是否仍被main使用 |
| --- | ---: | ---: | --- | --- |

### 8.2 表级映射

| 目标表 | 分类 | SQLite来源表 | 状态 | 记录量 | 转换方式 | 主要缺口 |
| --- | --- | --- | --- | ---: | --- | --- |

### 8.3 字段级映射

| 目标表.字段 | 必填 | SQLite表.字段 | 状态 | 非空率 | 语义/单位转换 | 样例 | 风险 |
| --- | --- | --- | --- | ---: | --- | --- | --- |

### 8.4 算法可运行性

| 算法步骤 | 所需数据 | 当前是否满足 | 可用记录量 | 缺口 | 结论 |
| --- | --- | --- | ---: | --- | --- |

算法步骤至少包括：技术链接、里程碑成熟度、产业任务抽取、JD召回、既有岗位覆盖、跨公司证据、任务缺口、任务社区、已有岗位比较和候选评分。

### 8.5 最终结论

分别给出：

- 基础数据字段覆盖率；
- 有效记录覆盖率；
- TETG-EJD v1 算法就绪度；
- 官方闭环数据就绪度；
- P0/P1/P2 缺失数据清单；
- 推荐迁移顺序。

## 9. 覆盖率计算建议

不要按“存在同名表”计分。建议：

```text
字段覆盖分 = Σ(字段权重 × 状态系数)

DIRECT      = 1.00
TRANSFORM   = 0.85
DERIVABLE   = 0.75
SAMPLE_ONLY = 0.35
UNCERTAIN   = 0.25
ABSENT      = 0.00
NOT_EXPECTED不进入基础数据分母
```

数据记录分再乘：非空率、可去重率、有效时间比例、来源可追溯率和人工抽样正确率。最终必须同时报告“字段结构覆盖”和“真实可用数据覆盖”，不能只给一个百分比。

## 10. 可直接交给另一位AI的提示词

```text
请只读审查 main 分支中的全部 SQLite 数据库，不修改代码和数据。

目标数据库结构见：database/target_schema_v1_mysql8.sql
核对规则见：docs/SQLite数据覆盖核对任务书.md
新岗位算法见：docs/新岗位发现算法设计_v1.md

请实际查询 SQLite 的表结构、行数、非空率、时间范围、独立企业数、来源URL、重复情况和真实样本，不要只比较表名。

对目标结构中的每个基础数据表和关键字段标记 DIRECT、TRANSFORM、DERIVABLE、SAMPLE_ONLY、ABSENT、NOT_EXPECTED 或 UNCERTAIN，并生成：
1. SQLite数据库及表清单；
2. 目标表映射；
3. 关键字段映射及非空率；
4. TETG-EJD v1每一步的数据可运行性；
5. 基础字段覆盖率、有效数据覆盖率和算法就绪度；
6. P0/P1/P2缺失数据与迁移建议。

特别检查：L1-L4和T1-T7是否被混淆；JD是否有真实原文、企业、来源和时间；里程碑是否有类型、日期、技术关系和来源；既有岗位是否有职责和能力基线；生成数据是否被误当成真实证据。
```
