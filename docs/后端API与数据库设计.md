# 后端API与数据库设计

> 项目：具身智能岗位能力图谱系统  
> 版本：v1.0  
> 日期：2026-08-08

---

## 一、数据库设计

### 1.1 总体ER关系

```
crawl_targets ──→ crawl_records ──→ raw_data
                                        │
                                        ├──→ job_descriptions ──→ job_clusters
                                        │                              │
                                        ├──→ tech_terms ←──────────────┘
                                        │         │
                                        └──→ milestones
                                                  
new_positions (独立)          capability_updates
resumes ──→ resume_profiles ──→ match_results
```

---

### 1.2 数据表定义

#### 表1：crawl_targets（爬取目标）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 主键 |
| name | TEXT | 目标名称 |
| url | TEXT | 爬取URL |
| type | TEXT | 类型：recruitment/company/government |
| crawl_frequency | TEXT | 爬取频率（cron表达式） |
| status | TEXT | 状态：active/paused/disabled |
| last_crawl_at | DATETIME | 上次爬取时间 |
| depth | INTEGER | 爬取深度（默认1） |
| config | JSON | 额外配置（选择器、规则等） |
| created_at | DATETIME | 创建时间 |
| updated_at | DATETIME | 更新时间 |

---

#### 表2：crawl_records（爬取记录）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 主键 |
| target_id | INTEGER FK | 关联爬取目标 |
| started_at | DATETIME | 开始时间 |
| finished_at | DATETIME | 结束时间 |
| status | TEXT | 状态：running/success/failed |
| new_items_count | INTEGER | 新增数据条数 |
| error_message | TEXT | 错误信息（如有） |

---

#### 表3：raw_data（原始数据）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 主键 |
| source_id | INTEGER FK | 来源（crawl_target或null=手动导入） |
| source_type | TEXT | 来源类型：crawl/manual |
| content_type | TEXT | 内容类型：jd/tech_news/report |
| raw_content | TEXT | 原始文本内容 |
| content_hash | TEXT | 内容hash（去重用） |
| source_url | TEXT | 来源URL |
| published_at | DATETIME | 原文发布时间 |
| crawled_at | DATETIME | 采集时间 |
| process_status | TEXT | 处理状态：pending/processed/failed |
| extracted_data | JSON | LLM提取后的结构化数据 |

---

#### 表4：tech_terms（技术词）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 主键 |
| name | TEXT UNIQUE | 技术词名称 |
| category | TEXT | 所属分类（与关键词分类标准一致） |
| sub_category | TEXT | 子分类 |
| description | TEXT | 描述/定义 |
| level | TEXT | 级别：basic/intermediate/advanced/expert |
| first_seen_at | DATETIME | 首次出现时间 |
| status | TEXT | 状态：active/emerging/deprecated |
| source | TEXT | 来源（首次发现的出处） |
| created_at | DATETIME | 创建时间 |
| updated_at | DATETIME | 更新时间 |

---

#### 表5：milestones（技术里程碑）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 主键 |
| title | TEXT | 里程碑标题 |
| description | TEXT | 详细描述 |
| tech_direction | TEXT | 所属技术方向 |
| occurred_at | DATETIME | 发生时间 |
| impact_scope | TEXT | 影响范围 |
| related_terms | JSON | 关联技术词ID列表 |
| source_url | TEXT | 来源链接 |
| confidence | REAL | 置信度 |
| status | TEXT | 状态：pending/confirmed/rejected |
| created_at | DATETIME | 创建时间 |

---

#### 表6：job_descriptions（岗位JD）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 主键 |
| raw_data_id | INTEGER FK | 关联原始数据 |
| title | TEXT | 岗位名称 |
| company | TEXT | 公司名称 |
| description | TEXT | 职责描述 |
| requirements | TEXT | 任职要求 |
| skills_required | JSON | 必备技能列表（技术词ID） |
| skills_bonus | JSON | 加分技能列表（技术词ID） |
| salary_range | TEXT | 薪资范围 |
| location | TEXT | 工作地点 |
| experience_required | TEXT | 经验要求 |
| education_required | TEXT | 学历要求 |
| published_at | DATETIME | 发布时间 |
| source_url | TEXT | 来源URL |
| cluster_id | INTEGER FK | 归属聚类（可为空） |
| is_duplicate | BOOLEAN | 是否为重复/抄袭 |
| duplicate_of | INTEGER FK | 重复源JD的ID |
| created_at | DATETIME | 入库时间 |

---

#### 表7：job_clusters（岗位聚类）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 主键 |
| name | TEXT | 聚类名称（岗位名称） |
| description | TEXT | 岗位描述 |
| category | TEXT | 所属分类 |
| jd_count | INTEGER | 关联JD数量 |
| status | TEXT | 状态：active/pending_review/archived |
| confidence | REAL | 聚类置信度（LLM评分） |
| is_predefined | BOOLEAN | 是否为预定义聚类 |
| created_by | TEXT | 创建方式：system/user/auto |
| created_at | DATETIME | 创建时间 |
| updated_at | DATETIME | 更新时间 |

---

#### 表8：cluster_term_relations（聚类-技术词关联）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 主键 |
| cluster_id | INTEGER FK | 聚类ID |
| term_id | INTEGER FK | 技术词ID |
| frequency | INTEGER | 在该聚类JD中出现的频率 |
| weight | REAL | 权重（基于频率+时间衰减计算） |
| requirement_type | TEXT | 类型：required/bonus |
| first_seen_at | DATETIME | 首次在该聚类出现的时间 |
| last_seen_at | DATETIME | 最近出现时间 |
| trend | TEXT | 趋势：rising/stable/declining |
| created_at | DATETIME | 创建时间 |
| updated_at | DATETIME | 更新时间 |

---

#### 表9：new_positions（新发现岗位）⭐ 独立表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 主键 |
| name | TEXT | 岗位名称 |
| core_responsibilities | TEXT | 核心职责 |
| required_skills | JSON | 必备技能（技术词ID列表） |
| bonus_skills | JSON | 加分技能（技术词ID列表） |
| industry_scenarios | TEXT | 典型行业应用场景 |
| full_jd | TEXT | 完整JD（细化后） |
| related_milestones | JSON | 关联里程碑ID列表 |
| trigger_terms | JSON | 触发发现的技术词组合 |
| confidence | REAL | 置信度评分 |
| status | TEXT | 状态：candidate/confirmed/rejected |
| review_note | TEXT | 审核备注 |
| created_at | DATETIME | 发现时间 |
| confirmed_at | DATETIME | 确认时间 |
| updated_at | DATETIME | 更新时间 |

---

#### 表10：capability_updates（能力更新事件）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 主键 |
| cluster_id | INTEGER FK | 关联聚类 |
| term_id | INTEGER FK | 关联技术词 |
| change_type | TEXT | 变更类型：added/removed/modified |
| description | TEXT | 变更说明 |
| evidence_source | TEXT | 证据来源（JD ID/URL） |
| confidence | REAL | 置信度 |
| status | TEXT | 状态：pending/confirmed/rejected |
| triggered_by | TEXT | 触发原因：new_jd/milestone/time_decay |
| created_at | DATETIME | 发生时间 |
| reviewed_at | DATETIME | 审核时间 |

---

#### 表11：resumes（简历）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 主键 |
| file_name | TEXT | 文件名 |
| file_type | TEXT | 文件类型：pdf/doc/txt/text |
| raw_text | TEXT | 提取的纯文本内容 |
| upload_method | TEXT | 上传方式：file/text_input |
| parse_status | TEXT | 解析状态：pending/parsing/done/failed |
| created_at | DATETIME | 上传时间 |

---

#### 表12：resume_profiles（求职者画像）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 主键 |
| resume_id | INTEGER FK | 关联简历 |
| target_position | TEXT | 求职意向岗位 |
| skills | JSON | 技术能力列表（含熟练度） |
| work_experience | JSON | 工作经历 |
| project_experience | JSON | 项目经验 |
| education | JSON | 教育背景 |
| total_years | REAL | 总工作年限 |
| work_style | TEXT | 工作风格 |
| development_direction | TEXT | 发展方向 |
| learning_potential | TEXT | 学习潜力评估 |
| strength_summary | TEXT | 综合优势摘要 |
| skill_depth_assessment | JSON | 能力深度评估 |
| created_at | DATETIME | 生成时间 |
| updated_at | DATETIME | 更新时间 |

---

#### 表13：match_results（匹配结果）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 主键 |
| resume_id | INTEGER FK | 关联简历 |
| profile_id | INTEGER FK | 关联画像 |
| target_type | TEXT | 目标类型：cluster/new_position |
| target_id | INTEGER FK | 目标岗位/聚类ID |
| overall_score | REAL | 总匹配分 |
| hard_skill_score | REAL | 硬性技能匹配分 |
| depth_score | REAL | 深度匹配分 |
| experience_score | REAL | 经验匹配分 |
| soft_match_score | REAL | 软性匹配分 |
| potential_score | REAL | 发展潜力分 |
| matched_skills | JSON | 匹配项 |
| missing_skills | JSON | 缺失项 |
| insufficient_skills | JSON | 不足项 |
| improvement_plan | JSON | 改进方案（短/中/长期） |
| learning_path | JSON | 学习路径 |
| created_at | DATETIME | 生成时间 |

---

#### 表14：llm_conversations（LLM对话记录）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 主键 |
| resume_id | INTEGER FK | 关联简历 |
| role | TEXT | 角色：assistant/user |
| content | TEXT | 消息内容 |
| created_at | DATETIME | 时间 |

---

#### 表15：system_settings（系统设置）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 主键 |
| key | TEXT UNIQUE | 配置键 |
| value | TEXT | 配置值 |
| category | TEXT | 分类：llm/crawler/algorithm/general |
| description | TEXT | 说明 |
| updated_at | DATETIME | 更新时间 |

---

## 二、后端API设计

### 2.1 API总览

基础路径：`/api/v1`

| 模块 | 前缀 | 说明 |
|------|------|------|
| 数据采集 | `/crawl` | 爬取目标管理、采集记录 |
| 数据管理 | `/data` | 原始数据、技术词、里程碑 |
| JD管理 | `/jd` | JD相关操作 |
| 岗位聚类 | `/cluster` | 聚类管理、能力更新 |
| 新岗位发现 | `/position` | 新岗位候选、审批 |
| 能力图谱 | `/graph` | 图谱数据查询 |
| 简历匹配 | `/resume` | 简历上传、解析、匹配 |
| 系统设置 | `/settings` | 配置管理 |
| 统计 | `/stats` | Dashboard统计数据 |

---

### 2.2 数据采集模块 API

```
GET    /api/v1/crawl/targets           # 获取所有爬取目标
POST   /api/v1/crawl/targets           # 新增爬取目标
PUT    /api/v1/crawl/targets/:id       # 更新爬取目标
DELETE /api/v1/crawl/targets/:id       # 删除爬取目标
POST   /api/v1/crawl/targets/:id/start # 手动触发爬取
POST   /api/v1/crawl/targets/:id/stop  # 停止爬取

GET    /api/v1/crawl/records           # 获取采集记录列表
GET    /api/v1/crawl/records/:id       # 获取单次采集详情
```

---

### 2.3 数据管理模块 API

```
# 原始数据
GET    /api/v1/data/raw                # 获取原始数据列表（分页、筛选）
GET    /api/v1/data/raw/:id            # 获取单条原始数据
POST   /api/v1/data/raw/import         # 手动导入数据

# 技术词
GET    /api/v1/data/terms              # 获取技术词列表
GET    /api/v1/data/terms/:id          # 获取单个技术词详情
POST   /api/v1/data/terms              # 新增技术词
PUT    /api/v1/data/terms/:id          # 更新技术词
GET    /api/v1/data/terms/categories   # 获取分类列表
GET    /api/v1/data/terms/trending     # 获取热门/趋势技术词

# 里程碑
GET    /api/v1/data/milestones         # 获取里程碑列表
GET    /api/v1/data/milestones/:id     # 获取单个里程碑
POST   /api/v1/data/milestones         # 新增里程碑
PUT    /api/v1/data/milestones/:id     # 更新/审批里程碑
```

---

### 2.4 JD管理模块 API

```
GET    /api/v1/jd                      # 获取JD列表（分页、筛选）
GET    /api/v1/jd/:id                  # 获取单个JD详情
POST   /api/v1/jd                      # 手动新增JD
PUT    /api/v1/jd/:id                  # 更新JD
DELETE /api/v1/jd/:id                  # 删除JD
POST   /api/v1/jd/cluster              # 触发JD聚类
GET    /api/v1/jd/duplicates           # 获取重复JD列表
```

---

### 2.5 岗位聚类模块 API

```
GET    /api/v1/cluster                 # 获取所有聚类列表
GET    /api/v1/cluster/:id             # 获取聚类详情（含能力集）
POST   /api/v1/cluster                 # 手动创建聚类
PUT    /api/v1/cluster/:id             # 更新聚类
DELETE /api/v1/cluster/:id             # 删除聚类
POST   /api/v1/cluster/:id/approve     # 审批通过待审聚类
POST   /api/v1/cluster/:id/reject      # 拒绝待审聚类

# 能力更新
GET    /api/v1/cluster/updates         # 获取能力更新事件列表
GET    /api/v1/cluster/updates/:id     # 获取单条更新详情
PUT    /api/v1/cluster/updates/:id     # 审批能力更新
GET    /api/v1/cluster/:id/terms       # 获取聚类的技术词列表
GET    /api/v1/cluster/:id/trend       # 获取聚类趋势数据
```

---

### 2.6 新岗位发现模块 API

```
GET    /api/v1/position                # 获取新岗位列表（筛选状态）
GET    /api/v1/position/:id            # 获取新岗位详情
POST   /api/v1/position/detect         # 手动触发新岗位检测
PUT    /api/v1/position/:id            # 编辑新岗位
POST   /api/v1/position/:id/confirm    # 确认入库
POST   /api/v1/position/:id/reject     # 拒绝
POST   /api/v1/position/:id/elaborate  # 细化为完整JD（调用LLM）
GET    /api/v1/position/history        # 获取已确认的新岗位历史
```

---

### 2.7 能力图谱模块 API

```
GET    /api/v1/graph/overview          # 获取图谱概览数据（全景）
GET    /api/v1/graph/association       # 获取岗位-能力关联数据
GET    /api/v1/graph/heatmap           # 获取热力图数据
GET    /api/v1/graph/evolution         # 获取演进图数据
GET    /api/v1/graph/node/:id          # 获取节点详情
GET    /api/v1/graph/node/:id/related  # 获取节点关联
```

**查询参数**（通用）：
- `category` — 按技术栈分类过滤
- `level` — 按级别过滤
- `cluster_id` — 按聚类过滤
- `limit` — 限制返回数量

---

### 2.8 简历匹配模块 API

```
# 简历管理
POST   /api/v1/resume/upload           # 上传简历文件
POST   /api/v1/resume/text             # 文本输入简历
GET    /api/v1/resume/:id/status       # 获取解析状态
GET    /api/v1/resume/:id/profile      # 获取求职者画像
PUT    /api/v1/resume/:id/profile      # 手动修正画像

# 对话交互
GET    /api/v1/resume/:id/chat         # 获取对话历史
POST   /api/v1/resume/:id/chat         # 发送消息（LLM对话）

# 匹配分析
POST   /api/v1/resume/:id/match        # 执行匹配分析
GET    /api/v1/resume/:id/match        # 获取匹配结果列表
GET    /api/v1/match/:id               # 获取单个匹配结果详情
```

**匹配请求体**：
```json
{
  "target_type": "cluster",        // 或 "new_position"
  "target_id": 1,
  "weights": {                      // 可选：自定义权重
    "hard_skill": 0.3,
    "depth": 0.2,
    "experience": 0.2,
    "soft": 0.15,
    "potential": 0.15
  }
}
```

---

### 2.9 系统设置模块 API

```
GET    /api/v1/settings                # 获取所有设置
GET    /api/v1/settings/:category      # 按分类获取设置
PUT    /api/v1/settings/:key           # 更新单个设置
POST   /api/v1/settings/batch          # 批量更新设置
```

---

### 2.10 统计模块 API

```
GET    /api/v1/stats/overview          # Dashboard概览统计
GET    /api/v1/stats/trends            # 趋势数据（技术词热度等）
GET    /api/v1/stats/recent-events     # 最近事件流
```

---

## 三、WebSocket接口（实时通信）

用于LLM流式输出和对话交互：

```
WS /ws/resume/:id/parse               # 简历解析实时进度
WS /ws/resume/:id/chat                # 对话交互（双向）
WS /ws/crawl/progress                 # 爬取进度推送
```

---

## 四、关键设计决策

### 4.1 新岗位 vs 岗位聚类 — 分离存储

- `new_positions` 表独立于 `job_clusters` 表
- 两者层级相同（都是"岗位"概念），但管理流程不同
- 匹配时两者都可作为目标（`target_type` 字段区分）

### 4.2 技术词统一库

- 所有技术词统一存储在 `tech_terms` 表
- JD、聚类、新岗位都通过ID引用技术词
- 避免技术词重复、不一致

### 4.3 JSON字段使用场景

- 用于灵活的多值字段（技能列表、关联关系等）
- 避免过多中间表，简化查询
- 关键查询字段仍用独立列+索引

### 4.4 置信度机制贯穿

- 里程碑、新岗位、聚类、能力更新都有 `confidence` 字段
- 前端根据置信度展示不同UI状态
- 高置信度自动通过，低置信度进入审批流

---

## 五、技术栈建议

| 层级 | 选择 | 说明 |
|------|------|------|
| 后端框架 | FastAPI (Python) | 异步支持好，自动OpenAPI文档 |
| 数据库 | SQLite → PostgreSQL | 开发用SQLite，生产可切换PG |
| ORM | SQLAlchemy / SQLite直接操作 | 根据复杂度选择 |
| LLM调用 | OpenAI兼容API (DeepSeek) | 统一接口 |
| 任务调度 | APScheduler | 轻量级定时任务 |
| 爬虫 | httpx + BeautifulSoup | 异步爬取 |
| 文本相似度 | simhash / minhash | JD去重 |
