-- ============================================================================
-- 统一数据库建表脚本（阶段 0 交付物）
-- 项目：多源异构数据驱动岗位和能力图谱构建与动态演化分析系统
-- 原则：单一事实源 —— 所有模块（管线/图谱/匹配/审核）读写同一套表，禁止平行表
-- 版本：v1.2  2026-08-08（阶段一：新增第 10 节技术演化域表；job_definitions 补新兴发现扩展列）
-- ============================================================================

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- ----------------------------------------------------------------------------
-- 1. 技能本体（L1 技术域 → L2 技术类 → L3 技术点 → L4 技术词）
-- ----------------------------------------------------------------------------

-- L1 技术域（新一代信息技术：AI / 大数据 / 物联网 / 智能系统）
CREATE TABLE IF NOT EXISTS domains (
    l1_code      TEXT PRIMARY KEY,              -- 如 'AI' / 'BD' / 'IOT' / 'IS'
    l1_name      TEXT NOT NULL,
    sort_order   INTEGER DEFAULT 0
);

-- L2 技术类
CREATE TABLE IF NOT EXISTS l2_categories (
    l2_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    l1_code      TEXT NOT NULL,
    l2_name      TEXT NOT NULL,
    UNIQUE (l1_code, l2_name),
    FOREIGN KEY (l1_code) REFERENCES domains(l1_code)
);

-- L3 技术点
CREATE TABLE IF NOT EXISTS l3_categories (
    l3_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    l2_id        INTEGER NOT NULL,
    l3_name      TEXT NOT NULL,
    UNIQUE (l2_id, l3_name),
    FOREIGN KEY (l2_id) REFERENCES l2_categories(l2_id)
);

-- L4 技术词（技能本体最小粒度，词典条目即技能）
CREATE TABLE IF NOT EXISTS skills (
    skill_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    skill_term     TEXT NOT NULL UNIQUE,        -- 规范技术词（keyword_norm）
    skill_term_raw TEXT,                        -- 词典原始写法
    l4_type        TEXT NOT NULL DEFAULT '细分词', -- 细分词 / 组合词 / 指标词 / 型号词（项目二原版四类）
    l3_id          INTEGER,
    l2_id          INTEGER,
    l1_code        TEXT,
    review_status  TEXT NOT NULL DEFAULT 'approved', -- 词典词条默认已审核
    source         TEXT NOT NULL DEFAULT 'dictionary', -- dictionary / embodied_db / llm / manual
    created_at     TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_skills_l1 ON skills(l1_code);
CREATE INDEX IF NOT EXISTS idx_skills_l3 ON skills(l3_id);

-- ----------------------------------------------------------------------------
-- 2. 岗位数据（多源导入，幂等去重）
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS jobs (
    job_id         TEXT PRIMARY KEY,
    title          TEXT NOT NULL,
    company        TEXT,
    city           TEXT,
    region         TEXT,
    salary_text    TEXT,
    salary_min     INTEGER,
    salary_max     INTEGER,
    experience     TEXT,
    education      TEXT,
    headcount      TEXT,
    jd_text        TEXT,
    source_file    TEXT,                        -- 来源文件名
    platform       TEXT,                        -- 来源平台
    collect_time   TEXT,                        -- 收录时间（时效字段）
    link           TEXT,
    dedup_key      TEXT,                        -- 幂等键：title+company+collect_time 归一化
    created_at     TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_dedup ON jobs(dedup_key) WHERE dedup_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_jobs_title ON jobs(title);
CREATE INDEX IF NOT EXISTS idx_jobs_city ON jobs(city);

-- ----------------------------------------------------------------------------
-- 3. 岗位-技能关联（图谱的边，带证据与置信度 —— 幻觉防控基础）
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS job_skills (
    job_id         TEXT NOT NULL,
    skill_id       INTEGER NOT NULL,
    keyword_raw    TEXT,                        -- 命中时的原始写法（源库迁移保留）
    evidence       TEXT,                        -- JD 原文证据片段（证据溯源；源库迁移批次可为空，由重提取回填）
    confidence     REAL NOT NULL DEFAULT 0.95,  -- 词典匹配默认高置信
    l4_type        TEXT,
    source         TEXT NOT NULL DEFAULT 'dictionary', -- dictionary / llm
    review_status  TEXT NOT NULL DEFAULT 'pending', -- pending / approved / rejected
    created_at     TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (job_id, skill_id),
    FOREIGN KEY (job_id) REFERENCES jobs(job_id),
    FOREIGN KEY (skill_id) REFERENCES skills(skill_id)
);
CREATE INDEX IF NOT EXISTS idx_job_skills_skill ON job_skills(skill_id);
CREATE INDEX IF NOT EXISTS idx_job_skills_status ON job_skills(review_status);

-- ----------------------------------------------------------------------------
-- 4. 岗位聚类（新岗位发现的技术路线）
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS clusters (
    cluster_id             TEXT PRIMARY KEY,
    cluster_name           TEXT,
    description            TEXT,
    shared_skills          TEXT,                -- JSON 数组
    representative_titles  TEXT,                -- JSON 数组
    keywords               TEXT,                -- JSON 数组
    job_count              INTEGER DEFAULT 0,
    name_source            TEXT DEFAULT 'heuristic', -- heuristic / llm
    review_status          TEXT NOT NULL DEFAULT 'pending',
    clustered_at           TEXT,
    created_at             TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS job_cluster_map (
    cluster_id   TEXT NOT NULL,
    job_id       TEXT NOT NULL,
    clustered_at TEXT,
    PRIMARY KEY (cluster_id, job_id),
    FOREIGN KEY (cluster_id) REFERENCES clusters(cluster_id),
    FOREIGN KEY (job_id) REFERENCES jobs(job_id)
);

-- 聚类映射回技术分类体系（L1→L2→L3）
CREATE TABLE IF NOT EXISTS cluster_classifications (
    cluster_id             TEXT PRIMARY KEY,
    job_count              INTEGER,
    primary_l1_code        TEXT,
    primary_l2_name        TEXT,
    primary_l2_coverage    REAL,
    primary_l3_name        TEXT,
    category_ratio         REAL,
    l1_distribution        TEXT,                -- JSON
    l2_distribution        TEXT,                -- JSON
    l3_distribution        TEXT,                -- JSON
    classified_at          TEXT,
    FOREIGN KEY (cluster_id) REFERENCES clusters(cluster_id)
);

-- ----------------------------------------------------------------------------
-- 5. 简历（阶段 3）
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS resumes (
    resume_id     TEXT PRIMARY KEY,
    file_name     TEXT,
    name          TEXT,
    title         TEXT,
    skills_json   TEXT,                         -- LLM 提取的结构化字段快照
    raw_text      TEXT,
    talent_type   TEXT,                         -- 人才类型（源库 talents 画像）
    university    TEXT,                         -- 单位/院校
    school_lab    TEXT,                         -- 院系/实验室
    research_direction TEXT,                    -- 研究方向
    achievements  TEXT,                         -- 代表性成果
    industry      TEXT,                         -- 产业背景
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS resume_skills (
    resume_id    TEXT NOT NULL,
    skill_id     INTEGER NOT NULL,
    confidence   REAL DEFAULT 0.9,
    source       TEXT NOT NULL DEFAULT 'llm',   -- llm / dictionary
    PRIMARY KEY (resume_id, skill_id),
    FOREIGN KEY (resume_id) REFERENCES resumes(resume_id),
    FOREIGN KEY (skill_id) REFERENCES skills(skill_id)
);

-- ----------------------------------------------------------------------------
-- 6. 人工审核记录（阶段 4：未审核不入正式表）
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS reviews (
    review_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    target_type   TEXT NOT NULL,                -- skill / job_skill / cluster / job_definition / evolution
    target_id     TEXT NOT NULL,                -- 目标主键（复合键用 JSON 表示）
    action        TEXT NOT NULL,                -- approve / reject / merge
    reviewer      TEXT DEFAULT 'admin',
    comment       TEXT,
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_reviews_target ON reviews(target_type, target_id);

-- ----------------------------------------------------------------------------
-- 7. 快照与差分（阶段 5：能力动态更新）
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS snapshots (
    snapshot_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    label         TEXT NOT NULL,                -- 如 'v1_2026-08'
    payload       TEXT NOT NULL,                -- job_skills 全量快照 JSON
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS snapshot_diffs (
    diff_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    base_snapshot INTEGER NOT NULL,
    new_snapshot  INTEGER NOT NULL,
    job_id        TEXT NOT NULL,
    change_type   TEXT NOT NULL,                -- added / removed / modified
    skill_id      INTEGER,
    detail        TEXT,                         -- 更新说明
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (base_snapshot) REFERENCES snapshots(snapshot_id),
    FOREIGN KEY (new_snapshot) REFERENCES snapshots(snapshot_id)
);

-- ----------------------------------------------------------------------------
-- 8. 新岗位定义（阶段 5：五要素）
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS job_definitions (
    definition_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    cluster_id        TEXT,                     -- 来源聚类（聚类发现路线）
    technology_id     TEXT,                     -- 来源技术实体（新兴发现路线，如 T1.02）
    job_type          TEXT,                     -- 新兴岗位 / 岗位演化 / 已有岗位（新兴发现路线）
    job_name          TEXT NOT NULL,            -- 要素1：岗位名称
    core_duties       TEXT,                     -- 要素2：核心职责
    required_skills   TEXT,                     -- 要素3：必备技能（JSON 数组）
    bonus_skills      TEXT,                     -- 要素4：加分技能（JSON 数组）
    industry_scenarios TEXT,                    -- 要素5：典型行业应用场景
    scores_json       TEXT,                     -- 候选岗位分项得分（新兴发现路线，JSON）
    evidence_json     TEXT,                     -- 证据链：里程碑 + JD 证据（新兴发现路线，JSON）
    generation_source TEXT DEFAULT 'llm',       -- llm / manual / emerging
    review_status     TEXT NOT NULL DEFAULT 'pending',
    created_at        TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (cluster_id) REFERENCES clusters(cluster_id)
);

-- ----------------------------------------------------------------------------
-- 9. 元数据
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pipeline_meta (
    key        TEXT PRIMARY KEY,
    value      TEXT,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ----------------------------------------------------------------------------
-- 10. 技术演化驱动的新岗位发现（移植自 embodied-job-evolution-lab）
--     路线：技术实体链接 → 里程碑成熟度 → 任务缺口 → 候选岗位（证据链）
-- ----------------------------------------------------------------------------

-- 技术实体主数据（L2/L3 标准实体 + 别名；technology_id 如 T1.02）
CREATE TABLE IF NOT EXISTS technologies (
    technology_id   TEXT PRIMARY KEY,
    standard_name   TEXT NOT NULL,
    level           TEXT NOT NULL,              -- L2 / L3 / NEW
    domain          TEXT,
    definition      TEXT,
    parent_id       TEXT,                       -- L3 → 所属 L2 编码
    aliases_json    TEXT,                       -- 别名/子级技术词（JSON 数组，用于 JD 召回）
    regex           TEXT,                       -- 归类别名正则（可选）
    mapped_l1_code  TEXT                        -- 映射统一本体 L1 域（如 T1）
);

-- 技术里程碑（事件类型加权 × 时间衰减 → 成熟度）
CREATE TABLE IF NOT EXISTS milestones (
    event_id             TEXT PRIMARY KEY,
    name                 TEXT NOT NULL,
    description          TEXT,
    event_date           TEXT,                  -- ISO 日期
    source               TEXT,
    technology_category  TEXT,                  -- 涉及技术类目（桥接映射键）
    event_type           TEXT,                  -- 技术演示/论文发表/开源发布/产品发布…
    technology_links     TEXT                   -- 桥接映射 JSON：[[技术编码, 权重], ...]
);

-- 算法知识层：能力模板（technology_code='fallback' 为兜底模板，{技术}为占位符）
CREATE TABLE IF NOT EXISTS capabilities (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    technology_code TEXT NOT NULL,
    name            TEXT NOT NULL,
    object          TEXT,
    scenario        TEXT,
    UNIQUE (technology_code, name)
);

-- 算法知识层：定制任务库（任务组 data/model/evaluation/planning/deployment）
CREATE TABLE IF NOT EXISTS tasks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    technology_code TEXT NOT NULL,
    name            TEXT NOT NULL,
    task_group      TEXT NOT NULL,
    keywords_json   TEXT NOT NULL,              -- 证据召回关键词（防幻觉：无关键词任务被过滤）
    relevance       REAL NOT NULL DEFAULT 0.9,
    UNIQUE (technology_code, name)
);

-- 算法知识层：任务组 → 岗位名称映射
CREATE TABLE IF NOT EXISTS role_titles (
    technology_code TEXT NOT NULL,
    task_group      TEXT NOT NULL,
    title           TEXT NOT NULL,
    PRIMARY KEY (technology_code, task_group)
);

-- 新兴岗位预测运行记录（替代 lab 的 JSON 文件持久化，落统一库）
CREATE TABLE IF NOT EXISTS emerging_runs (
    run_id         TEXT PRIMARY KEY,
    technology_id  TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'completed', -- completed / failed
    request_json   TEXT,                        -- 请求参数快照
    result_json    TEXT,                        -- 完整结果（技术/能力/任务/候选岗位/指标）
    error          TEXT,
    created_at     TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at   TEXT
);
CREATE INDEX IF NOT EXISTS idx_emerging_runs_tech ON emerging_runs(technology_id);
