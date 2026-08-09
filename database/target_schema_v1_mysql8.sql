-- ============================================================================
-- 具身智能岗位与能力图谱系统：目标数据库结构 v1
-- 数据库：MySQL 8.0.16+
-- 设计来源：当前项目需求、后端数据流设计、TETG-EJD v1 算法设计
-- 注意：本文件为全新目标结构，不以项目中已有 SQL 为基线。
--
-- 数据覆盖分类：
-- [A] 基础真实数据：应检查旧 SQLite 是否已有可映射数据
-- [B] 派生数据：可由 A 类数据和算法重新计算，不要求旧库预先具备
-- [C] 运行数据：新系统运行、审核、画像或匹配后产生
-- ============================================================================

CREATE DATABASE IF NOT EXISTS embodied_job_graph_v1
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_0900_ai_ci;

USE embodied_job_graph_v1;
SET NAMES utf8mb4;

-- ============================================================================
-- 1. 账号、机构与数据来源
-- ============================================================================

-- [C] 应用账号
CREATE TABLE app_user (
  user_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  user_code VARCHAR(64) NOT NULL UNIQUE,
  display_name VARCHAR(200) NOT NULL,
  user_role_code VARCHAR(32) NOT NULL COMMENT 'admin/reviewer/applicant/hr',
  account_status_code VARCHAR(32) NOT NULL DEFAULT 'active',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CHECK (account_status_code IN ('active','disabled','deleted'))
) ENGINE=InnoDB COMMENT='[C] 应用账号，不保存第三方明文凭据';

-- [A] 企业、政府、高校、研究机构、行业组织等统一主体
CREATE TABLE md_organization (
  organization_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  organization_code VARCHAR(64) NOT NULL UNIQUE,
  canonical_name VARCHAR(500) NOT NULL,
  normalized_name VARCHAR(500) NOT NULL,
  organization_type_code VARCHAR(32) NOT NULL
    COMMENT 'enterprise/government/university/research/association/platform/other',
  country_code VARCHAR(16) NULL,
  province_name VARCHAR(100) NULL,
  city_name VARCHAR(100) NULL,
  website_url VARCHAR(1500) NULL,
  industry_text VARCHAR(500) NULL,
  organization_status_code VARCHAR(32) NOT NULL DEFAULT 'active',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  KEY idx_org_name (normalized_name),
  KEY idx_org_type_region (organization_type_code, province_name, city_name)
) ENGINE=InnoDB COMMENT='[A] 数据中涉及的独立机构主体';

-- [A] 机构别名，用于企业去重和跨公司统计
CREATE TABLE md_organization_alias (
  organization_alias_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  organization_id BIGINT UNSIGNED NOT NULL,
  alias_text VARCHAR(500) NOT NULL,
  normalized_alias VARCHAR(500) NOT NULL,
  alias_type_code VARCHAR(32) NOT NULL DEFAULT 'source',
  UNIQUE KEY uk_org_alias (organization_id, normalized_alias),
  KEY idx_org_alias_lookup (normalized_alias),
  FOREIGN KEY (organization_id) REFERENCES md_organization(organization_id)
) ENGINE=InnoDB COMMENT='[A] 机构原名、简称和历史名称';

-- [A] 用户维护的数据源对象
CREATE TABLE md_data_source (
  data_source_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  source_code VARCHAR(64) NOT NULL UNIQUE,
  source_name VARCHAR(300) NOT NULL,
  source_type_code VARCHAR(32) NOT NULL
    COMMENT 'recruitment/company/government/industry/manual/file/api',
  owner_organization_id BIGINT UNSIGNED NULL,
  entry_url VARCHAR(1500) NULL,
  content_type_code VARCHAR(32) NOT NULL
    COMMENT 'job/milestone/technology/mixed',
  authority_level_code VARCHAR(32) NULL,
  independent_source_group VARCHAR(128) NULL COMMENT '转载链或同源平台归组',
  default_reliability_score DECIMAL(5,2) NULL,
  license_note TEXT NULL,
  source_status_code VARCHAR(32) NOT NULL DEFAULT 'active',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  FOREIGN KEY (owner_organization_id) REFERENCES md_organization(organization_id),
  CHECK (default_reliability_score IS NULL OR default_reliability_score BETWEEN 0 AND 100),
  CHECK (source_status_code IN ('active','paused','blocked','retired'))
) ENGINE=InnoDB COMMENT='[A] 数据采集源及基础质量属性';

-- [A/C] 数据源的采集和合规策略
CREATE TABLE md_source_collection_policy (
  collection_policy_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  data_source_id BIGINT UNSIGNED NOT NULL,
  policy_version VARCHAR(32) NOT NULL,
  list_rule_json JSON NULL,
  detail_rule_json JSON NULL,
  pagination_rule_json JSON NULL,
  max_depth TINYINT UNSIGNED NOT NULL DEFAULT 1,
  schedule_expression VARCHAR(128) NULL,
  schedule_timezone VARCHAR(64) NOT NULL DEFAULT 'Asia/Shanghai',
  rate_limit_per_minute INT UNSIGNED NULL,
  domain_concurrency INT UNSIGNED NOT NULL DEFAULT 1,
  robots_status_code VARCHAR(32) NULL,
  terms_checked_at DATETIME NULL,
  allowed_scope_text TEXT NULL,
  parser_code VARCHAR(64) NULL,
  is_active TINYINT(1) NOT NULL DEFAULT 1,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_source_policy_version (data_source_id, policy_version),
  FOREIGN KEY (data_source_id) REFERENCES md_data_source(data_source_id),
  CHECK (max_depth <= 1)
) ENGINE=InnoDB COMMENT='[A/C] 列表、详情、分页、调度、限速和合规配置';

-- [C] 一次采集运行
CREATE TABLE biz_collection_run (
  collection_run_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  run_code VARCHAR(64) NOT NULL UNIQUE,
  data_source_id BIGINT UNSIGNED NOT NULL,
  collection_policy_id BIGINT UNSIGNED NOT NULL,
  scheduled_at DATETIME NULL,
  started_at DATETIME NULL,
  completed_at DATETIME NULL,
  run_status_code VARCHAR(32) NOT NULL DEFAULT 'pending',
  discovered_count INT UNSIGNED NOT NULL DEFAULT 0,
  changed_count INT UNSIGNED NOT NULL DEFAULT 0,
  unchanged_count INT UNSIGNED NOT NULL DEFAULT 0,
  failed_count INT UNSIGNED NOT NULL DEFAULT 0,
  input_cursor_json JSON NULL,
  output_cursor_json JSON NULL,
  error_summary TEXT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (data_source_id) REFERENCES md_data_source(data_source_id),
  FOREIGN KEY (collection_policy_id) REFERENCES md_source_collection_policy(collection_policy_id),
  CHECK (run_status_code IN ('pending','running','success','partial_success','failed','cancelled')),
  KEY idx_collection_run_source_time (data_source_id, started_at, run_status_code)
) ENGINE=InnoDB COMMENT='[C] 定时或手工采集的一次运行';

-- [C] 采集运行内的每次列表或详情请求
CREATE TABLE biz_collection_request (
  collection_request_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  collection_run_id BIGINT UNSIGNED NOT NULL,
  parent_request_id BIGINT UNSIGNED NULL,
  request_url VARCHAR(1500) NOT NULL,
  normalized_url_hash CHAR(64) NOT NULL,
  request_depth TINYINT UNSIGNED NOT NULL DEFAULT 0,
  request_type_code VARCHAR(32) NOT NULL COMMENT 'list/detail/file/api',
  response_status_code INT NULL,
  response_hash CHAR(64) NULL,
  response_asset_id BIGINT UNSIGNED NULL,
  retry_count INT UNSIGNED NOT NULL DEFAULT 0,
  request_status_code VARCHAR(32) NOT NULL DEFAULT 'pending',
  parse_status_code VARCHAR(32) NULL,
  error_code VARCHAR(64) NULL,
  started_at DATETIME NULL,
  completed_at DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_collection_request (collection_run_id, normalized_url_hash),
  FOREIGN KEY (collection_run_id) REFERENCES biz_collection_run(collection_run_id),
  FOREIGN KEY (parent_request_id) REFERENCES biz_collection_request(collection_request_id),
  CHECK (request_depth <= 1),
  CHECK (request_status_code IN ('pending','running','success','failed','skipped')),
  KEY idx_collection_request_status (collection_run_id, request_status_code, request_depth)
) ENGINE=InnoDB COMMENT='[C] 每次列表和一级详情请求的响应、重试与错误';

-- [A/C] HTML、PDF、DOCX、图片和OCR产物
CREATE TABLE raw_file_asset (
  file_asset_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  asset_code VARCHAR(64) NOT NULL UNIQUE,
  asset_type_code VARCHAR(32) NOT NULL COMMENT 'html/pdf/docx/txt/image/ocr/json/export',
  storage_object_key VARCHAR(1500) NOT NULL,
  original_file_name VARCHAR(500) NULL,
  mime_type VARCHAR(200) NULL,
  file_size_bytes BIGINT UNSIGNED NULL,
  sha256_hash CHAR(64) NOT NULL,
  virus_scan_status_code VARCHAR(32) NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_file_asset_hash_type (sha256_hash, asset_type_code)
) ENGINE=InnoDB COMMENT='[A/C] 原始文件和中间产物的对象存储索引';

ALTER TABLE biz_collection_request
  ADD CONSTRAINT fk_collection_request_asset
  FOREIGN KEY (response_asset_id) REFERENCES raw_file_asset(file_asset_id);

-- [A] 稳定的网页或文档身份
CREATE TABLE raw_source_document (
  source_document_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  document_code VARCHAR(64) NOT NULL UNIQUE,
  data_source_id BIGINT UNSIGNED NOT NULL,
  document_type_code VARCHAR(32) NOT NULL
    COMMENT 'job/milestone/technology/policy/patent/paper/standard/product/resume/other',
  source_record_key VARCHAR(500) NULL,
  canonical_url VARCHAR(1500) NULL,
  document_identity_key CHAR(64) NOT NULL COMMENT '来源业务键或规范URL的哈希',
  title VARCHAR(1000) NULL,
  first_seen_at DATETIME NOT NULL,
  last_seen_at DATETIME NOT NULL,
  missing_successive_runs INT UNSIGNED NOT NULL DEFAULT 0,
  document_status_code VARCHAR(32) NOT NULL DEFAULT 'active',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_source_document_identity (data_source_id, document_identity_key),
  FOREIGN KEY (data_source_id) REFERENCES md_data_source(data_source_id),
  CHECK (document_status_code IN ('active','suspected_expired','expired','deleted','superseded')),
  KEY idx_document_type_seen (document_type_code, last_seen_at)
) ENGINE=InnoDB COMMENT='[A] 原始材料的稳定身份和存续状态';

-- [A] 原始材料内容版本
CREATE TABLE raw_source_document_version (
  source_document_version_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  source_document_id BIGINT UNSIGNED NOT NULL,
  collection_run_id BIGINT UNSIGNED NULL,
  version_no INT UNSIGNED NOT NULL,
  previous_version_id BIGINT UNSIGNED NULL,
  file_asset_id BIGINT UNSIGNED NULL,
  published_at DATETIME NULL,
  collected_at DATETIME NOT NULL,
  valid_from DATETIME NOT NULL,
  valid_to DATETIME NULL,
  content_text LONGTEXT NOT NULL,
  content_json JSON NULL,
  content_hash CHAR(64) NOT NULL,
  parser_version VARCHAR(64) NULL,
  is_current TINYINT(1) NOT NULL DEFAULT 1,
  current_document_guard BIGINT UNSIGNED GENERATED ALWAYS AS
    (CASE WHEN is_current = 1 THEN source_document_id ELSE NULL END) STORED,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_document_version_no (source_document_id, version_no),
  UNIQUE KEY uk_document_content_hash (source_document_id, content_hash),
  UNIQUE KEY uk_document_one_current (current_document_guard),
  FOREIGN KEY (source_document_id) REFERENCES raw_source_document(source_document_id),
  FOREIGN KEY (collection_run_id) REFERENCES biz_collection_run(collection_run_id),
  FOREIGN KEY (previous_version_id) REFERENCES raw_source_document_version(source_document_version_id),
  FOREIGN KEY (file_asset_id) REFERENCES raw_file_asset(file_asset_id),
  CHECK (valid_to IS NULL OR valid_from < valid_to),
  KEY idx_document_current (source_document_id, is_current, valid_from)
) ENGINE=InnoDB COMMENT='[A] 原始材料的不可变内容版本';

-- [B] 文档清洗和质量评分
CREATE TABLE biz_document_quality (
  document_quality_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  source_document_version_id BIGINT UNSIGNED NOT NULL,
  checker_version VARCHAR(64) NOT NULL,
  timeliness_score DECIMAL(5,2) NULL,
  completeness_score DECIMAL(5,2) NULL,
  noise_score DECIMAL(5,2) NULL,
  duplication_score DECIMAL(5,2) NULL,
  requirement_inflation_score DECIMAL(5,2) NULL,
  ai_generated_risk_score DECIMAL(5,2) NULL,
  prompt_injection_risk_score DECIMAL(5,2) NULL,
  overall_quality_score DECIMAL(5,2) NULL,
  quality_status_code VARCHAR(32) NOT NULL,
  reason_json JSON NULL,
  checked_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_document_quality_version (source_document_version_id, checker_version),
  FOREIGN KEY (source_document_version_id)
    REFERENCES raw_source_document_version(source_document_version_id),
  CHECK (quality_status_code IN ('accepted','warning','rejected')),
  CHECK (overall_quality_score IS NULL OR overall_quality_score BETWEEN 0 AND 100)
) ENGINE=InnoDB COMMENT='[B] 时滞、噪声、复制、通胀和提示词注入风险';

-- [B] 近重复文档簇
CREATE TABLE biz_duplicate_document_group (
  duplicate_group_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  group_code VARCHAR(64) NOT NULL UNIQUE,
  representative_document_version_id BIGINT UNSIGNED NULL,
  detection_method_code VARCHAR(32) NOT NULL,
  algorithm_version VARCHAR(64) NOT NULL,
  member_count INT UNSIGNED NOT NULL DEFAULT 0,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (representative_document_version_id)
    REFERENCES raw_source_document_version(source_document_version_id)
) ENGINE=InnoDB COMMENT='[B] 转载、抄袭或模板化文档簇';

CREATE TABLE rel_duplicate_document_member (
  duplicate_group_id BIGINT UNSIGNED NOT NULL,
  source_document_version_id BIGINT UNSIGNED NOT NULL,
  similarity_score DECIMAL(7,6) NOT NULL,
  copied_ratio DECIMAL(7,6) NULL,
  is_representative TINYINT(1) NOT NULL DEFAULT 0,
  PRIMARY KEY (duplicate_group_id, source_document_version_id),
  FOREIGN KEY (duplicate_group_id) REFERENCES biz_duplicate_document_group(duplicate_group_id),
  FOREIGN KEY (source_document_version_id)
    REFERENCES raw_source_document_version(source_document_version_id),
  CHECK (similarity_score BETWEEN 0 AND 1)
) ENGINE=InnoDB COMMENT='[B] 重复簇成员和相似度';

-- ============================================================================
-- 2. 抽取、证据、验证和审核
-- ============================================================================

-- [C] 一次规则、模型或LLM抽取运行
CREATE TABLE biz_extraction_run (
  extraction_run_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  run_code VARCHAR(64) NOT NULL UNIQUE,
  source_document_version_id BIGINT UNSIGNED NOT NULL,
  task_type_code VARCHAR(32) NOT NULL
    COMMENT 'document_parse/jd_parse/milestone_parse/technology_extract/resume_parse',
  extractor_type_code VARCHAR(32) NOT NULL COMMENT 'rule/model/llm/hybrid',
  model_name VARCHAR(100) NULL,
  model_version VARCHAR(100) NULL,
  prompt_version VARCHAR(64) NULL,
  schema_version VARCHAR(64) NOT NULL,
  parameter_json JSON NULL,
  input_hash CHAR(64) NOT NULL,
  raw_output_json JSON NULL,
  run_status_code VARCHAR(32) NOT NULL DEFAULT 'pending',
  started_at DATETIME NULL,
  completed_at DATETIME NULL,
  error_message TEXT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (source_document_version_id)
    REFERENCES raw_source_document_version(source_document_version_id),
  CHECK (run_status_code IN ('pending','running','success','failed','cancelled')),
  KEY idx_extraction_document_task (source_document_version_id, task_type_code, run_status_code)
) ENGINE=InnoDB COMMENT='[C] 可复现的结构化抽取运行';

-- [A/B] 可定位到原文的证据片段
CREATE TABLE biz_evidence_span (
  evidence_span_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  source_document_version_id BIGINT UNSIGNED NOT NULL,
  span_type_code VARCHAR(32) NOT NULL
    COMMENT 'title/responsibility/requirement/scenario/timeline/result/other',
  page_no INT UNSIGNED NULL,
  start_offset INT UNSIGNED NULL,
  end_offset INT UNSIGNED NULL,
  evidence_text TEXT NOT NULL,
  evidence_hash CHAR(64) NOT NULL,
  source_reliability_score DECIMAL(5,2) NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_evidence_hash (source_document_version_id, evidence_hash),
  FOREIGN KEY (source_document_version_id)
    REFERENCES raw_source_document_version(source_document_version_id),
  CHECK (start_offset IS NULL OR end_offset IS NULL OR start_offset <= end_offset)
) ENGINE=InnoDB COMMENT='[A/B] JD、里程碑和简历事实的原文证据';

-- [B/C] 尚未发布的结构化事实
CREATE TABLE biz_extracted_fact (
  extracted_fact_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  extraction_run_id BIGINT UNSIGNED NOT NULL,
  fact_type_code VARCHAR(64) NOT NULL,
  subject_text VARCHAR(500) NULL,
  predicate_code VARCHAR(64) NOT NULL,
  object_text TEXT NOT NULL,
  normalized_target_type VARCHAR(32) NULL,
  normalized_target_id BIGINT UNSIGNED NULL,
  extraction_confidence DECIMAL(5,2) NOT NULL,
  fact_hash CHAR(64) NOT NULL,
  verification_status_code VARCHAR(32) NOT NULL DEFAULT 'unverified',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_extracted_fact (extraction_run_id, fact_hash),
  FOREIGN KEY (extraction_run_id) REFERENCES biz_extraction_run(extraction_run_id),
  CHECK (extraction_confidence BETWEEN 0 AND 100),
  CHECK (verification_status_code IN ('unverified','verified','rejected','needs_review'))
) ENGINE=InnoDB COMMENT='[B/C] 验证前不得进入正式库的候选事实';

CREATE TABLE rel_fact_evidence (
  extracted_fact_id BIGINT UNSIGNED NOT NULL,
  evidence_span_id BIGINT UNSIGNED NOT NULL,
  support_type_code VARCHAR(32) NOT NULL DEFAULT 'support',
  support_score DECIMAL(5,2) NULL,
  PRIMARY KEY (extracted_fact_id, evidence_span_id, support_type_code),
  FOREIGN KEY (extracted_fact_id) REFERENCES biz_extracted_fact(extracted_fact_id),
  FOREIGN KEY (evidence_span_id) REFERENCES biz_evidence_span(evidence_span_id),
  CHECK (support_type_code IN ('support','contradict'))
) ENGINE=InnoDB COMMENT='[B/C] 候选事实的支持证据和反证';

CREATE TABLE biz_fact_validation (
  fact_validation_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  extracted_fact_id BIGINT UNSIGNED NOT NULL,
  validation_type_code VARCHAR(32) NOT NULL
    COMMENT 'schema/rule/cross_source/rag/consistency/human',
  validator_version VARCHAR(64) NOT NULL,
  validation_result_code VARCHAR(32) NOT NULL,
  validation_score DECIMAL(5,2) NULL,
  supporting_source_count INT UNSIGNED NOT NULL DEFAULT 0,
  independent_organization_count INT UNSIGNED NOT NULL DEFAULT 0,
  contradiction_count INT UNSIGNED NOT NULL DEFAULT 0,
  explanation_text TEXT NULL,
  validated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_fact_validation (extracted_fact_id, validation_type_code, validator_version),
  FOREIGN KEY (extracted_fact_id) REFERENCES biz_extracted_fact(extracted_fact_id),
  CHECK (validation_result_code IN ('pass','warning','fail'))
) ENGINE=InnoDB COMMENT='[B/C] 事实交叉验证和幻觉风险检查';

-- [C] 数据审核和新岗位专项审核的统一任务壳
CREATE TABLE biz_review_task (
  review_task_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  review_code VARCHAR(64) NOT NULL UNIQUE,
  queue_code VARCHAR(32) NOT NULL COMMENT 'data_review/emerging_job_review',
  target_type_code VARCHAR(64) NOT NULL,
  target_id BIGINT UNSIGNED NOT NULL,
  risk_reason_code VARCHAR(64) NULL,
  priority_code VARCHAR(16) NOT NULL DEFAULT 'medium',
  review_status_code VARCHAR(32) NOT NULL DEFAULT 'queued',
  assigned_user_id BIGINT UNSIGNED NULL,
  due_at DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  FOREIGN KEY (assigned_user_id) REFERENCES app_user(user_id),
  CHECK (review_status_code IN ('queued','assigned','reviewing','approved','rejected','needs_revision','merged')),
  KEY idx_review_queue (queue_code, review_status_code, priority_code, created_at)
) ENGINE=InnoDB COMMENT='[C] 可领取、退回和重审的审核工作项';

CREATE TABLE biz_review_action (
  review_action_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  review_task_id BIGINT UNSIGNED NOT NULL,
  reviewer_user_id BIGINT UNSIGNED NOT NULL,
  action_code VARCHAR(32) NOT NULL COMMENT 'claim/approve/reject/modify/return/merge',
  before_json JSON NULL,
  after_json JSON NULL,
  comment_text TEXT NULL,
  acted_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (review_task_id) REFERENCES biz_review_task(review_task_id),
  FOREIGN KEY (reviewer_user_id) REFERENCES app_user(user_id),
  KEY idx_review_action_history (review_task_id, acted_at)
) ENGINE=InnoDB COMMENT='[C] 审核操作和修改前后快照';

-- ============================================================================
-- 3. L1-L4技术主数据、T1-T7领域和能力本体
-- ============================================================================

-- [A] L轴分类版本
CREATE TABLE md_technology_taxonomy_version (
  taxonomy_version_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  version_code VARCHAR(32) NOT NULL UNIQUE,
  version_name VARCHAR(200) NOT NULL,
  previous_version_id BIGINT UNSIGNED NULL,
  effective_date DATE NOT NULL,
  version_status_code VARCHAR(32) NOT NULL DEFAULT 'draft',
  change_summary TEXT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (previous_version_id)
    REFERENCES md_technology_taxonomy_version(taxonomy_version_id),
  CHECK (version_status_code IN ('draft','active','retired'))
) ENGINE=InnoDB COMMENT='[A] L1-L4技术分类版本';

-- [A] L1-L4统一节点，L3为图谱默认标准技术点，L4为表面词
CREATE TABLE md_technology_node (
  technology_node_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  taxonomy_version_id BIGINT UNSIGNED NOT NULL,
  technology_code VARCHAR(64) NOT NULL,
  parent_technology_node_id BIGINT UNSIGNED NULL,
  level_code VARCHAR(8) NOT NULL COMMENT 'L1/L2/L3/L4',
  technology_name VARCHAR(500) NOT NULL,
  normalized_name VARCHAR(500) NOT NULL,
  node_type_code VARCHAR(32) NOT NULL DEFAULT 'standard',
  semantic_role_code VARCHAR(32) NULL
    COMMENT 'method/tool/hardware/task/metric/product/scenario/other',
  definition_text TEXT NULL,
  governance_status_code VARCHAR(32) NOT NULL DEFAULT 'active',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uk_technology_version_code (taxonomy_version_id, technology_code),
  UNIQUE KEY uk_technology_parent_name (taxonomy_version_id, parent_technology_node_id, normalized_name),
  FOREIGN KEY (taxonomy_version_id)
    REFERENCES md_technology_taxonomy_version(taxonomy_version_id),
  FOREIGN KEY (parent_technology_node_id) REFERENCES md_technology_node(technology_node_id),
  CHECK (level_code IN ('L1','L2','L3','L4')),
  CHECK (governance_status_code IN ('active','pending_review','deprecated')),
  KEY idx_technology_level (taxonomy_version_id, level_code, governance_status_code)
) ENGINE=InnoDB COMMENT='[A] L1-L4技术标准节点';

-- [A] 技术别名、缩写和原始表面词
CREATE TABLE md_technology_alias (
  technology_alias_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  technology_node_id BIGINT UNSIGNED NOT NULL,
  alias_text VARCHAR(500) NOT NULL,
  normalized_alias VARCHAR(500) NOT NULL,
  alias_type_code VARCHAR(32) NOT NULL COMMENT 'allowed/source/abbreviation/regex/deprecated',
  is_matchable TINYINT(1) NOT NULL DEFAULT 1,
  UNIQUE KEY uk_technology_alias (technology_node_id, normalized_alias),
  KEY idx_technology_alias_lookup (normalized_alias, is_matchable),
  FOREIGN KEY (technology_node_id) REFERENCES md_technology_node(technology_node_id)
) ENGINE=InnoDB COMMENT='[A] 技术节点别名和识别表达';

-- [A] 独立于L轴的T1-T7领域
CREATE TABLE md_technology_domain (
  technology_domain_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  domain_version VARCHAR(32) NOT NULL,
  domain_code VARCHAR(8) NOT NULL COMMENT 'T1-T7',
  domain_name VARCHAR(200) NOT NULL,
  definition_text TEXT NULL,
  color_token VARCHAR(32) NULL,
  sort_order TINYINT UNSIGNED NOT NULL,
  is_active TINYINT(1) NOT NULL DEFAULT 1,
  UNIQUE KEY uk_technology_domain (domain_version, domain_code),
  CHECK (domain_code IN ('T1','T2','T3','T4','T5','T6','T7'))
) ENGINE=InnoDB COMMENT='[A] T1-T7七类技术领域';

-- [A/B] L节点到T领域的多标签归属
CREATE TABLE rel_technology_node_domain (
  technology_node_id BIGINT UNSIGNED NOT NULL,
  technology_domain_id BIGINT UNSIGNED NOT NULL,
  domain_score DECIMAL(7,4) NOT NULL,
  is_primary TINYINT(1) NOT NULL DEFAULT 0,
  evidence_count INT UNSIGNED NOT NULL DEFAULT 0,
  calculation_version VARCHAR(64) NULL,
  review_status_code VARCHAR(32) NOT NULL DEFAULT 'confirmed',
  PRIMARY KEY (technology_node_id, technology_domain_id),
  FOREIGN KEY (technology_node_id) REFERENCES md_technology_node(technology_node_id),
  FOREIGN KEY (technology_domain_id) REFERENCES md_technology_domain(technology_domain_id),
  CHECK (domain_score BETWEEN 0 AND 100)
) ENGINE=InnoDB COMMENT='[A/B] 技术点的主域、次域、得分和证据';

-- [A] 广义能力本体，含技术、任务和通用能力
CREATE TABLE md_capability (
  capability_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  capability_code VARCHAR(64) NOT NULL UNIQUE,
  parent_capability_id BIGINT UNSIGNED NULL,
  capability_name VARCHAR(300) NOT NULL,
  normalized_name VARCHAR(300) NOT NULL,
  capability_type_code VARCHAR(32) NOT NULL
    COMMENT 'technical/task/general/domain/management',
  capability_level TINYINT UNSIGNED NOT NULL,
  definition_text TEXT NULL,
  measurement_rule TEXT NULL,
  ontology_version VARCHAR(32) NOT NULL,
  is_active TINYINT(1) NOT NULL DEFAULT 1,
  UNIQUE KEY uk_capability_version_name (ontology_version, parent_capability_id, normalized_name),
  FOREIGN KEY (parent_capability_id) REFERENCES md_capability(capability_id)
) ENGINE=InnoDB COMMENT='[A] 用于岗位和画像匹配的能力本体';

-- [A] 技术类能力到L3技术点的映射
CREATE TABLE rel_capability_technology (
  capability_id BIGINT UNSIGNED NOT NULL,
  technology_node_id BIGINT UNSIGNED NOT NULL,
  relation_type_code VARCHAR(32) NOT NULL DEFAULT 'maps_to',
  is_primary TINYINT(1) NOT NULL DEFAULT 0,
  confidence_score DECIMAL(5,2) NULL,
  mapping_method_code VARCHAR(32) NULL,
  PRIMARY KEY (capability_id, technology_node_id, relation_type_code),
  FOREIGN KEY (capability_id) REFERENCES md_capability(capability_id),
  FOREIGN KEY (technology_node_id) REFERENCES md_technology_node(technology_node_id)
) ENGINE=InnoDB COMMENT='[A] 广义能力与L3技术标准点的桥接';

-- [A/B] 技术点的前置、演化、应用和相关关系
CREATE TABLE rel_technology_relation (
  from_technology_node_id BIGINT UNSIGNED NOT NULL,
  to_technology_node_id BIGINT UNSIGNED NOT NULL,
  relation_type_code VARCHAR(32) NOT NULL
    COMMENT 'related/prerequisite/evolution/application/component/replaces',
  relation_weight DECIMAL(7,4) NULL,
  confidence_score DECIMAL(5,2) NULL,
  evidence_summary TEXT NULL,
  PRIMARY KEY (from_technology_node_id, to_technology_node_id, relation_type_code),
  FOREIGN KEY (from_technology_node_id) REFERENCES md_technology_node(technology_node_id),
  FOREIGN KEY (to_technology_node_id) REFERENCES md_technology_node(technology_node_id),
  CHECK (from_technology_node_id <> to_technology_node_id)
) ENGINE=InnoDB COMMENT='[A/B] 非树状技术关系';

-- [A/C] 未命中正式技术主数据的候选词
CREATE TABLE biz_technology_term_candidate (
  technology_term_candidate_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  normalized_term VARCHAR(500) NOT NULL,
  representative_raw_term VARCHAR(500) NOT NULL,
  first_evidence_span_id BIGINT UNSIGNED NULL,
  occurrence_document_count INT UNSIGNED NOT NULL DEFAULT 1,
  independent_organization_count INT UNSIGNED NOT NULL DEFAULT 0,
  candidate_status_code VARCHAR(32) NOT NULL DEFAULT 'pending',
  suggested_parent_id BIGINT UNSIGNED NULL,
  approved_technology_node_id BIGINT UNSIGNED NULL,
  reviewed_by_user_id BIGINT UNSIGNED NULL,
  reviewed_at DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (first_evidence_span_id) REFERENCES biz_evidence_span(evidence_span_id),
  FOREIGN KEY (suggested_parent_id) REFERENCES md_technology_node(technology_node_id),
  FOREIGN KEY (approved_technology_node_id) REFERENCES md_technology_node(technology_node_id),
  FOREIGN KEY (reviewed_by_user_id) REFERENCES app_user(user_id),
  CHECK (candidate_status_code IN ('pending','reviewing','approved','rejected','merged')),
  KEY idx_term_candidate_review (candidate_status_code, occurrence_document_count)
) ENGINE=InnoDB COMMENT='[A/C] 新技术词候选池';

-- [B/C] 一次批量技术词标准化运行
CREATE TABLE biz_technology_mapping_run (
  technology_mapping_run_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  run_code VARCHAR(64) NOT NULL UNIQUE,
  taxonomy_version_id BIGINT UNSIGNED NOT NULL,
  entity_type_code VARCHAR(32) NOT NULL COMMENT 'job/milestone/profile/organization/document',
  algorithm_version VARCHAR(64) NOT NULL,
  model_version VARCHAR(100) NULL,
  input_count INT UNSIGNED NOT NULL DEFAULT 0,
  mapped_count INT UNSIGNED NOT NULL DEFAULT 0,
  candidate_count INT UNSIGNED NOT NULL DEFAULT 0,
  run_status_code VARCHAR(32) NOT NULL DEFAULT 'pending',
  started_at DATETIME NULL,
  completed_at DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (taxonomy_version_id)
    REFERENCES md_technology_taxonomy_version(taxonomy_version_id),
  CHECK (run_status_code IN ('pending','running','success','failed','cancelled'))
) ENGINE=InnoDB COMMENT='[B/C] 技术词精确、别名、向量和人工映射运行';

CREATE TABLE biz_technology_mapping_result (
  technology_mapping_result_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  technology_mapping_run_id BIGINT UNSIGNED NOT NULL,
  entity_type_code VARCHAR(32) NOT NULL,
  entity_id BIGINT UNSIGNED NOT NULL,
  source_field_name VARCHAR(128) NULL,
  raw_term VARCHAR(500) NOT NULL,
  normalized_term VARCHAR(500) NOT NULL,
  mapped_technology_node_id BIGINT UNSIGNED NULL,
  technology_term_candidate_id BIGINT UNSIGNED NULL,
  mapping_method_code VARCHAR(32) NOT NULL
    COMMENT 'exact/alias/regex/vector/llm_rerank/manual/unmapped',
  confidence_score DECIMAL(5,2) NULL,
  review_status_code VARCHAR(32) NOT NULL DEFAULT 'unreviewed',
  evidence_span_id BIGINT UNSIGNED NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_technology_mapping_result
    (technology_mapping_run_id, entity_type_code, entity_id, source_field_name, normalized_term),
  FOREIGN KEY (technology_mapping_run_id)
    REFERENCES biz_technology_mapping_run(technology_mapping_run_id),
  FOREIGN KEY (mapped_technology_node_id) REFERENCES md_technology_node(technology_node_id),
  FOREIGN KEY (technology_term_candidate_id)
    REFERENCES biz_technology_term_candidate(technology_term_candidate_id),
  FOREIGN KEY (evidence_span_id) REFERENCES biz_evidence_span(evidence_span_id),
  CHECK ((mapping_method_code = 'unmapped' AND mapped_technology_node_id IS NULL
      AND technology_term_candidate_id IS NOT NULL)
    OR (mapping_method_code <> 'unmapped' AND mapped_technology_node_id IS NOT NULL)),
  CHECK (confidence_score IS NULL OR confidence_score BETWEEN 0 AND 100)
) ENGINE=InnoDB COMMENT='[B/C] 原始技术表达到标准技术点的逐条映射和证据';

-- [A] 行业和应用场景
CREATE TABLE md_application_scenario (
  application_scenario_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  scenario_code VARCHAR(64) NOT NULL UNIQUE,
  scenario_name VARCHAR(300) NOT NULL,
  normalized_name VARCHAR(300) NOT NULL UNIQUE,
  definition_text TEXT NULL,
  parent_scenario_id BIGINT UNSIGNED NULL,
  is_active TINYINT(1) NOT NULL DEFAULT 1,
  FOREIGN KEY (parent_scenario_id) REFERENCES md_application_scenario(application_scenario_id)
) ENGINE=InnoDB COMMENT='[A] 岗位、任务和里程碑的应用场景';

-- ============================================================================
-- 4. 技术里程碑
-- ============================================================================

-- [A/C] 候选和正式里程碑共表，通过验证状态区分
CREATE TABLE biz_milestone_event (
  milestone_event_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  milestone_code VARCHAR(64) NOT NULL UNIQUE,
  milestone_name VARCHAR(1000) NOT NULL,
  normalized_name VARCHAR(1000) NOT NULL,
  milestone_type_code VARCHAR(32) NOT NULL
    COMMENT 'demo/paper/breakthrough/open_source/product/platform/deployment/standard_policy/other',
  event_date DATE NULL,
  event_year SMALLINT UNSIGNED NOT NULL,
  description_text LONGTEXT NULL,
  maturity_delta_code VARCHAR(32) NULL,
  primary_organization_id BIGINT UNSIGNED NULL,
  source_document_version_id BIGINT UNSIGNED NULL,
  extraction_run_id BIGINT UNSIGNED NULL,
  verification_status_code VARCHAR(32) NOT NULL DEFAULT 'candidate',
  confidence_score DECIMAL(5,2) NULL,
  approved_by_user_id BIGINT UNSIGNED NULL,
  approved_at DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (primary_organization_id) REFERENCES md_organization(organization_id),
  FOREIGN KEY (source_document_version_id)
    REFERENCES raw_source_document_version(source_document_version_id),
  FOREIGN KEY (extraction_run_id) REFERENCES biz_extraction_run(extraction_run_id),
  FOREIGN KEY (approved_by_user_id) REFERENCES app_user(user_id),
  CHECK (verification_status_code IN ('candidate','reviewing','verified','rejected','superseded')),
  CHECK (confidence_score IS NULL OR confidence_score BETWEEN 0 AND 100),
  KEY idx_milestone_time_type (event_date, milestone_type_code, verification_status_code)
) ENGINE=InnoDB COMMENT='[A/C] 技术里程碑候选、审核和正式事件';

CREATE TABLE rel_milestone_technology (
  milestone_event_id BIGINT UNSIGNED NOT NULL,
  technology_node_id BIGINT UNSIGNED NOT NULL,
  relation_type_code VARCHAR(32) NOT NULL DEFAULT 'supports',
  relevance_score DECIMAL(5,2) NOT NULL,
  mapping_method_code VARCHAR(32) NULL,
  is_human_confirmed TINYINT(1) NOT NULL DEFAULT 0,
  PRIMARY KEY (milestone_event_id, technology_node_id, relation_type_code),
  FOREIGN KEY (milestone_event_id) REFERENCES biz_milestone_event(milestone_event_id),
  FOREIGN KEY (technology_node_id) REFERENCES md_technology_node(technology_node_id),
  CHECK (relevance_score BETWEEN 0 AND 100)
) ENGINE=InnoDB COMMENT='[A/B] 里程碑到技术点的关系';

CREATE TABLE rel_milestone_scenario (
  milestone_event_id BIGINT UNSIGNED NOT NULL,
  application_scenario_id BIGINT UNSIGNED NOT NULL,
  relevance_score DECIMAL(5,2) NULL,
  PRIMARY KEY (milestone_event_id, application_scenario_id),
  FOREIGN KEY (milestone_event_id) REFERENCES biz_milestone_event(milestone_event_id),
  FOREIGN KEY (application_scenario_id) REFERENCES md_application_scenario(application_scenario_id)
) ENGINE=InnoDB COMMENT='[A/B] 里程碑的应用场景';

CREATE TABLE rel_milestone_evidence (
  milestone_event_id BIGINT UNSIGNED NOT NULL,
  evidence_span_id BIGINT UNSIGNED NOT NULL,
  support_type_code VARCHAR(32) NOT NULL DEFAULT 'support',
  support_score DECIMAL(5,2) NOT NULL,
  PRIMARY KEY (milestone_event_id, evidence_span_id, support_type_code),
  FOREIGN KEY (milestone_event_id) REFERENCES biz_milestone_event(milestone_event_id),
  FOREIGN KEY (evidence_span_id) REFERENCES biz_evidence_span(evidence_span_id),
  CHECK (support_type_code IN ('support','contradict'))
) ENGINE=InnoDB COMMENT='[A/B] 里程碑的原文支持证据和反证';

-- ============================================================================
-- 5. 真实JD、职责、要求和场景
-- ============================================================================

-- [A] 只保存真实招聘材料，禁止写入生成标准JD
CREATE TABLE biz_job_posting (
  job_posting_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  job_code VARCHAR(64) NOT NULL UNIQUE,
  source_document_version_id BIGINT UNSIGNED NOT NULL UNIQUE,
  data_source_id BIGINT UNSIGNED NOT NULL,
  source_job_id VARCHAR(300) NULL,
  organization_id BIGINT UNSIGNED NULL,
  company_name_raw VARCHAR(500) NULL,
  job_title_raw VARCHAR(1000) NOT NULL,
  job_title_normalized VARCHAR(500) NOT NULL,
  employment_type_code VARCHAR(32) NULL,
  job_level_code VARCHAR(32) NULL COMMENT 'intern/junior/middle/senior/expert/lead/unknown',
  region_text VARCHAR(300) NULL,
  salary_text VARCHAR(300) NULL,
  salary_min_monthly_cny DECIMAL(12,2) NULL,
  salary_max_monthly_cny DECIMAL(12,2) NULL,
  salary_months_per_year DECIMAL(4,1) NULL,
  education_code VARCHAR(32) NULL,
  education_text VARCHAR(200) NULL,
  experience_min_years DECIMAL(4,1) NULL,
  experience_max_years DECIMAL(4,1) NULL,
  experience_text VARCHAR(200) NULL,
  jd_clean_text LONGTEXT NOT NULL,
  published_at DATETIME NULL,
  collected_at DATETIME NOT NULL,
  expired_at DATETIME NULL,
  posting_status_code VARCHAR(32) NOT NULL DEFAULT 'active',
  parse_confidence_score DECIMAL(5,2) NULL,
  publish_score DECIMAL(5,2) NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  FOREIGN KEY (source_document_version_id)
    REFERENCES raw_source_document_version(source_document_version_id),
  FOREIGN KEY (data_source_id) REFERENCES md_data_source(data_source_id),
  FOREIGN KEY (organization_id) REFERENCES md_organization(organization_id),
  CHECK (posting_status_code IN ('active','suspected_expired','expired','removed')),
  CHECK (salary_min_monthly_cny IS NULL OR salary_max_monthly_cny IS NULL
    OR salary_min_monthly_cny <= salary_max_monthly_cny),
  CHECK (experience_min_years IS NULL OR experience_max_years IS NULL
    OR experience_min_years <= experience_max_years),
  KEY idx_job_title_time (job_title_normalized, published_at),
  KEY idx_job_org_status (organization_id, posting_status_code, collected_at)
) ENGINE=InnoDB COMMENT='[A] 去重、验证并正式发布的真实招聘JD';

-- [A/B] JD核心职责
CREATE TABLE biz_job_responsibility (
  job_responsibility_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  job_posting_id BIGINT UNSIGNED NOT NULL,
  responsibility_no INT UNSIGNED NOT NULL,
  raw_text TEXT NOT NULL,
  normalized_task_text TEXT NULL,
  action_verb VARCHAR(100) NULL,
  task_object VARCHAR(500) NULL,
  expected_output VARCHAR(500) NULL,
  confidence_score DECIMAL(5,2) NULL,
  UNIQUE KEY uk_job_responsibility_no (job_posting_id, responsibility_no),
  FOREIGN KEY (job_posting_id) REFERENCES biz_job_posting(job_posting_id)
) ENGINE=InnoDB COMMENT='[A/B] JD职责和产业任务结构';

-- [A/B] JD必需、加分和前沿要求；技术点与广义能力必须二选一
CREATE TABLE biz_job_requirement (
  job_requirement_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  job_posting_id BIGINT UNSIGNED NOT NULL,
  requirement_no INT UNSIGNED NOT NULL,
  requirement_type_code VARCHAR(32) NOT NULL COMMENT 'required/bonus/frontier',
  raw_term VARCHAR(500) NULL,
  raw_text TEXT NOT NULL,
  technology_node_id BIGINT UNSIGNED NULL,
  capability_id BIGINT UNSIGNED NULL,
  required_level_code VARCHAR(32) NULL COMMENT 'aware/familiar/proficient/expert/unspecified',
  required_level_score DECIMAL(5,2) NULL,
  mention_count INT UNSIGNED NOT NULL DEFAULT 1,
  mapping_method_code VARCHAR(32) NULL,
  confidence_score DECIMAL(5,2) NOT NULL,
  UNIQUE KEY uk_job_requirement_no (job_posting_id, requirement_no),
  FOREIGN KEY (job_posting_id) REFERENCES biz_job_posting(job_posting_id),
  FOREIGN KEY (technology_node_id) REFERENCES md_technology_node(technology_node_id),
  FOREIGN KEY (capability_id) REFERENCES md_capability(capability_id),
  CHECK ((technology_node_id IS NOT NULL) + (capability_id IS NOT NULL) = 1),
  CHECK (requirement_type_code IN ('required','bonus','frontier')),
  CHECK (required_level_score IS NULL OR required_level_score BETWEEN 0 AND 100),
  CHECK (confidence_score BETWEEN 0 AND 100),
  KEY idx_job_requirement_technology (technology_node_id, requirement_type_code, job_posting_id),
  KEY idx_job_requirement_capability (capability_id, requirement_type_code, job_posting_id)
) ENGINE=InnoDB COMMENT='[A/B] JD标准技术点或广义能力要求';

CREATE TABLE rel_job_scenario (
  job_posting_id BIGINT UNSIGNED NOT NULL,
  application_scenario_id BIGINT UNSIGNED NOT NULL,
  relevance_score DECIMAL(5,2) NULL,
  confidence_score DECIMAL(5,2) NULL,
  PRIMARY KEY (job_posting_id, application_scenario_id),
  FOREIGN KEY (job_posting_id) REFERENCES biz_job_posting(job_posting_id),
  FOREIGN KEY (application_scenario_id) REFERENCES md_application_scenario(application_scenario_id)
) ENGINE=InnoDB COMMENT='[A/B] JD的行业和应用场景';

-- [A/B] 统一把JD职责、要求和场景回指到原文证据
CREATE TABLE rel_job_fact_evidence (
  job_fact_evidence_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  job_posting_id BIGINT UNSIGNED NOT NULL,
  target_type_code VARCHAR(32) NOT NULL COMMENT 'responsibility/requirement/scenario/header',
  target_id BIGINT UNSIGNED NOT NULL COMMENT '由target_type_code解释',
  evidence_span_id BIGINT UNSIGNED NOT NULL,
  support_type_code VARCHAR(32) NOT NULL DEFAULT 'support',
  support_score DECIMAL(5,2) NOT NULL,
  UNIQUE KEY uk_job_fact_evidence (target_type_code, target_id, evidence_span_id, support_type_code),
  FOREIGN KEY (job_posting_id) REFERENCES biz_job_posting(job_posting_id),
  FOREIGN KEY (evidence_span_id) REFERENCES biz_evidence_span(evidence_span_id),
  CHECK (target_type_code IN ('responsibility','requirement','scenario','header')),
  CHECK (support_type_code IN ('support','contradict'))
) ENGINE=InnoDB COMMENT='[A/B] JD结构化字段的原文证据';

-- ============================================================================
-- 6. 岗位聚类、统一岗位和版本演化
-- ============================================================================

-- [B] 一次增量或全量岗位聚类运行
CREATE TABLE biz_job_clustering_run (
  clustering_run_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  run_code VARCHAR(64) NOT NULL UNIQUE,
  run_type_code VARCHAR(32) NOT NULL COMMENT 'incremental/full/recalibration',
  target_date DATE NOT NULL,
  window_start_date DATE NULL,
  feature_version VARCHAR(64) NOT NULL,
  embedding_model_version VARCHAR(100) NULL,
  algorithm_name VARCHAR(100) NOT NULL,
  algorithm_version VARCHAR(64) NOT NULL,
  parameter_json JSON NOT NULL,
  input_job_count INT UNSIGNED NOT NULL DEFAULT 0,
  output_cluster_count INT UNSIGNED NOT NULL DEFAULT 0,
  quality_metric_json JSON NULL,
  run_status_code VARCHAR(32) NOT NULL DEFAULT 'pending',
  started_at DATETIME NULL,
  completed_at DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CHECK (run_status_code IN ('pending','running','success','failed','cancelled'))
) ENGINE=InnoDB COMMENT='[B] 岗位聚类运行和参数快照';

-- [B] 某次运行得到的岗位簇版本
CREATE TABLE biz_job_cluster_version (
  job_cluster_version_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  clustering_run_id BIGINT UNSIGNED NOT NULL,
  stable_cluster_code VARCHAR(64) NOT NULL,
  cluster_label VARCHAR(300) NOT NULL,
  cluster_description TEXT NULL,
  member_count INT UNSIGNED NOT NULL DEFAULT 0,
  centroid_asset_id BIGINT UNSIGNED NULL,
  silhouette_score DECIMAL(8,6) NULL,
  coherence_score DECIMAL(5,2) NULL,
  cluster_status_code VARCHAR(32) NOT NULL DEFAULT 'active',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_cluster_run_stable (clustering_run_id, stable_cluster_code),
  FOREIGN KEY (clustering_run_id) REFERENCES biz_job_clustering_run(clustering_run_id),
  FOREIGN KEY (centroid_asset_id) REFERENCES raw_file_asset(file_asset_id),
  CHECK (cluster_status_code IN ('active','needs_review','ended'))
) ENGINE=InnoDB COMMENT='[B] 可版本化的JD岗位聚类';

-- [B] JD在某次聚类中的成员关系和Top-K分配证据
CREATE TABLE rel_job_cluster_member (
  job_cluster_version_id BIGINT UNSIGNED NOT NULL,
  job_posting_id BIGINT UNSIGNED NOT NULL,
  similarity_score DECIMAL(7,6) NOT NULL,
  assignment_method_code VARCHAR(32) NOT NULL COMMENT 'rule/model/manual/hybrid',
  assignment_confidence DECIMAL(5,2) NULL,
  top_candidates_json JSON NULL,
  is_representative TINYINT(1) NOT NULL DEFAULT 0,
  PRIMARY KEY (job_cluster_version_id, job_posting_id),
  FOREIGN KEY (job_cluster_version_id) REFERENCES biz_job_cluster_version(job_cluster_version_id),
  FOREIGN KEY (job_posting_id) REFERENCES biz_job_posting(job_posting_id),
  CHECK (similarity_score BETWEEN 0 AND 1),
  KEY idx_cluster_member_job (job_posting_id, job_cluster_version_id)
) ENGINE=InnoDB COMMENT='[B] 聚类成员、分数和候选归属';

-- [B] 聚类延续、拆分、合并、新生和结束
CREATE TABLE rel_job_cluster_lineage (
  from_cluster_version_id BIGINT UNSIGNED NULL,
  to_cluster_version_id BIGINT UNSIGNED NULL,
  lineage_type_code VARCHAR(32) NOT NULL COMMENT 'continued/split/merged/born/ended',
  member_overlap_score DECIMAL(7,6) NULL,
  explanation_text TEXT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_cluster_lineage (from_cluster_version_id, to_cluster_version_id, lineage_type_code),
  FOREIGN KEY (from_cluster_version_id) REFERENCES biz_job_cluster_version(job_cluster_version_id),
  FOREIGN KEY (to_cluster_version_id) REFERENCES biz_job_cluster_version(job_cluster_version_id),
  CHECK (from_cluster_version_id IS NOT NULL OR to_cluster_version_id IS NOT NULL)
) ENGINE=InnoDB COMMENT='[B] 跨期聚类谱系';

CREATE TABLE rel_job_cluster_domain (
  job_cluster_version_id BIGINT UNSIGNED NOT NULL,
  technology_domain_id BIGINT UNSIGNED NOT NULL,
  domain_score DECIMAL(5,2) NOT NULL,
  is_primary TINYINT(1) NOT NULL DEFAULT 0,
  evidence_count INT UNSIGNED NOT NULL DEFAULT 0,
  calculation_version VARCHAR(64) NOT NULL,
  review_status_code VARCHAR(32) NOT NULL DEFAULT 'unreviewed',
  PRIMARY KEY (job_cluster_version_id, technology_domain_id),
  FOREIGN KEY (job_cluster_version_id) REFERENCES biz_job_cluster_version(job_cluster_version_id),
  FOREIGN KEY (technology_domain_id) REFERENCES md_technology_domain(technology_domain_id),
  CHECK (domain_score BETWEEN 0 AND 100)
) ENGINE=InnoDB COMMENT='[B] 岗位聚类的T1-T7领域分布';

-- [A/C] 稳定的统一正式岗位；existing和emerging同级
CREATE TABLE biz_job_role (
  job_role_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  role_code VARCHAR(64) NOT NULL UNIQUE,
  canonical_name VARCHAR(300) NOT NULL UNIQUE,
  normalized_name VARCHAR(300) NOT NULL UNIQUE,
  origin_type_code VARCHAR(32) NOT NULL COMMENT 'cluster_derived/inference_derived/manual',
  lifecycle_status_code VARCHAR(32) NOT NULL DEFAULT 'active',
  first_detected_at DATETIME NULL,
  approved_at DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CHECK (origin_type_code IN ('cluster_derived','inference_derived','manual')),
  CHECK (lifecycle_status_code IN ('candidate','active','declining','retired'))
) ENGINE=InnoDB COMMENT='[A/C] 聚类岗位和推演岗位统一的稳定岗位实体';

CREATE TABLE md_job_role_alias (
  job_role_alias_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  job_role_id BIGINT UNSIGNED NOT NULL,
  alias_text VARCHAR(500) NOT NULL,
  normalized_alias VARCHAR(500) NOT NULL,
  alias_type_code VARCHAR(32) NOT NULL COMMENT 'source/common/historical/generated/deprecated',
  is_searchable TINYINT(1) NOT NULL DEFAULT 1,
  UNIQUE KEY uk_role_alias (job_role_id, normalized_alias),
  KEY idx_role_alias_lookup (normalized_alias, is_searchable),
  FOREIGN KEY (job_role_id) REFERENCES biz_job_role(job_role_id)
) ENGINE=InnoDB COMMENT='[A/C] 正式岗位别名和历史名称';

-- [A/B/C] 岗位定义和能力要求版本
CREATE TABLE biz_job_role_version (
  job_role_version_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  job_role_id BIGINT UNSIGNED NOT NULL,
  version_no INT UNSIGNED NOT NULL,
  previous_version_id BIGINT UNSIGNED NULL,
  valid_from DATE NOT NULL,
  valid_to DATE NULL,
  role_name VARCHAR(300) NOT NULL,
  one_line_definition TEXT NOT NULL,
  core_responsibility_text LONGTEXT NOT NULL,
  job_level_distribution_json JSON NULL,
  update_summary TEXT NULL,
  generation_method_code VARCHAR(32) NOT NULL COMMENT 'initial/statistical/llm/manual/hybrid',
  evidence_strength_score DECIMAL(5,2) NULL,
  approval_status_code VARCHAR(32) NOT NULL DEFAULT 'pending',
  current_role_guard BIGINT UNSIGNED GENERATED ALWAYS AS
    (CASE WHEN approval_status_code = 'approved' AND valid_to IS NULL
      THEN job_role_id ELSE NULL END) STORED,
  approved_by_user_id BIGINT UNSIGNED NULL,
  approved_at DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_role_version_no (job_role_id, version_no),
  UNIQUE KEY uk_role_one_current_version (current_role_guard),
  FOREIGN KEY (job_role_id) REFERENCES biz_job_role(job_role_id),
  FOREIGN KEY (previous_version_id) REFERENCES biz_job_role_version(job_role_version_id),
  FOREIGN KEY (approved_by_user_id) REFERENCES app_user(user_id),
  CHECK (valid_to IS NULL OR valid_from < valid_to),
  CHECK (approval_status_code IN ('pending','reviewing','approved','rejected','retired')),
  KEY idx_role_version_current (job_role_id, approval_status_code, valid_to)
) ENGINE=InnoDB COMMENT='[A/B/C] 正式岗位定义和要求的历史版本';

-- [A/B/C] 岗位版本的必需、加分和前沿要求
CREATE TABLE rel_job_role_version_requirement (
  role_version_requirement_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  job_role_version_id BIGINT UNSIGNED NOT NULL,
  technology_node_id BIGINT UNSIGNED NULL,
  capability_id BIGINT UNSIGNED NULL,
  requirement_type_code VARCHAR(32) NOT NULL,
  required_level_code VARCHAR(32) NULL,
  required_level_score DECIMAL(5,2) NULL,
  long_term_importance_score DECIMAL(5,2) NOT NULL,
  recent_activity_score DECIMAL(5,2) NOT NULL,
  coverage_rate DECIMAL(9,6) NULL,
  supporting_job_count INT UNSIGNED NOT NULL DEFAULT 0,
  independent_organization_count INT UNSIGNED NOT NULL DEFAULT 0,
  independent_source_count INT UNSIGNED NOT NULL DEFAULT 0,
  last_seen_at DATETIME NULL,
  confidence_score DECIMAL(5,2) NOT NULL,
  is_human_edited TINYINT(1) NOT NULL DEFAULT 0,
  FOREIGN KEY (job_role_version_id) REFERENCES biz_job_role_version(job_role_version_id),
  FOREIGN KEY (technology_node_id) REFERENCES md_technology_node(technology_node_id),
  FOREIGN KEY (capability_id) REFERENCES md_capability(capability_id),
  CHECK ((technology_node_id IS NOT NULL) + (capability_id IS NOT NULL) = 1),
  CHECK (requirement_type_code IN ('required','bonus','frontier')),
  CHECK (long_term_importance_score BETWEEN 0 AND 100),
  CHECK (recent_activity_score BETWEEN 0 AND 100),
  CHECK (confidence_score BETWEEN 0 AND 100),
  UNIQUE KEY uk_role_version_technology
    (job_role_version_id, technology_node_id, requirement_type_code),
  UNIQUE KEY uk_role_version_capability
    (job_role_version_id, capability_id, requirement_type_code),
  KEY idx_role_requirement_graph
    (job_role_version_id, requirement_type_code, long_term_importance_score)
) ENGINE=InnoDB COMMENT='[A/B/C] 岗位版本要求、长期重要度和近期活跃度';

CREATE TABLE rel_job_role_version_scenario (
  job_role_version_id BIGINT UNSIGNED NOT NULL,
  application_scenario_id BIGINT UNSIGNED NOT NULL,
  relevance_score DECIMAL(5,2) NOT NULL,
  evidence_count INT UNSIGNED NOT NULL DEFAULT 0,
  PRIMARY KEY (job_role_version_id, application_scenario_id),
  FOREIGN KEY (job_role_version_id) REFERENCES biz_job_role_version(job_role_version_id),
  FOREIGN KEY (application_scenario_id) REFERENCES md_application_scenario(application_scenario_id)
) ENGINE=InnoDB COMMENT='[A/B/C] 岗位版本的典型应用场景';

CREATE TABLE rel_job_role_version_domain (
  job_role_version_id BIGINT UNSIGNED NOT NULL,
  technology_domain_id BIGINT UNSIGNED NOT NULL,
  domain_score DECIMAL(5,2) NOT NULL,
  is_primary TINYINT(1) NOT NULL DEFAULT 0,
  evidence_count INT UNSIGNED NOT NULL DEFAULT 0,
  PRIMARY KEY (job_role_version_id, technology_domain_id),
  FOREIGN KEY (job_role_version_id) REFERENCES biz_job_role_version(job_role_version_id),
  FOREIGN KEY (technology_domain_id) REFERENCES md_technology_domain(technology_domain_id)
) ENGINE=InnoDB COMMENT='[A/B/C] 正式岗位版本的T1-T7领域分布';

-- [B/C] 聚类版本与稳定岗位的对应
CREATE TABLE rel_job_cluster_role (
  job_cluster_version_id BIGINT UNSIGNED NOT NULL,
  job_role_id BIGINT UNSIGNED NOT NULL,
  relation_type_code VARCHAR(32) NOT NULL COMMENT 'represents/supports/split_from/merged_into',
  confidence_score DECIMAL(5,2) NULL,
  is_primary TINYINT(1) NOT NULL DEFAULT 1,
  PRIMARY KEY (job_cluster_version_id, job_role_id, relation_type_code),
  FOREIGN KEY (job_cluster_version_id) REFERENCES biz_job_cluster_version(job_cluster_version_id),
  FOREIGN KEY (job_role_id) REFERENCES biz_job_role(job_role_id)
) ENGINE=InnoDB COMMENT='[B/C] 算法聚类与稳定业务岗位的桥接';

-- [B/C] 正式岗位或岗位要求的证据绑定
CREATE TABLE rel_job_role_evidence (
  job_role_evidence_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  job_role_version_id BIGINT UNSIGNED NOT NULL,
  role_version_requirement_id BIGINT UNSIGNED NULL,
  evidence_span_id BIGINT UNSIGNED NOT NULL,
  evidence_role_code VARCHAR(32) NOT NULL
    COMMENT 'name/definition/responsibility/requirement/scenario/change',
  support_type_code VARCHAR(32) NOT NULL DEFAULT 'support',
  support_score DECIMAL(5,2) NOT NULL,
  source_organization_id BIGINT UNSIGNED NULL,
  UNIQUE KEY uk_role_evidence
    (job_role_version_id, role_version_requirement_id, evidence_span_id, evidence_role_code),
  FOREIGN KEY (job_role_version_id) REFERENCES biz_job_role_version(job_role_version_id),
  FOREIGN KEY (role_version_requirement_id)
    REFERENCES rel_job_role_version_requirement(role_version_requirement_id),
  FOREIGN KEY (evidence_span_id) REFERENCES biz_evidence_span(evidence_span_id),
  FOREIGN KEY (source_organization_id) REFERENCES md_organization(organization_id),
  CHECK (support_type_code IN ('support','contradict'))
) ENGINE=InnoDB COMMENT='[B/C] 岗位定义、职责、能力和变化的原文证据';

CREATE TABLE biz_job_evolution_event (
  job_evolution_event_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  event_code VARCHAR(64) NOT NULL UNIQUE,
  job_role_id BIGINT UNSIGNED NOT NULL,
  from_role_version_id BIGINT UNSIGNED NULL,
  to_role_version_id BIGINT UNSIGNED NOT NULL,
  event_type_code VARCHAR(32) NOT NULL COMMENT 'created/updated/merged/split/retired',
  change_summary LONGTEXT NOT NULL,
  confidence_score DECIMAL(5,2) NOT NULL,
  approval_status_code VARCHAR(32) NOT NULL DEFAULT 'pending',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (job_role_id) REFERENCES biz_job_role(job_role_id),
  FOREIGN KEY (from_role_version_id) REFERENCES biz_job_role_version(job_role_version_id),
  FOREIGN KEY (to_role_version_id) REFERENCES biz_job_role_version(job_role_version_id),
  CHECK (event_type_code IN ('created','updated','merged','split','retired')),
  CHECK (approval_status_code IN ('pending','reviewing','approved','rejected'))
) ENGINE=InnoDB COMMENT='[B/C] 新岗位创建和既有岗位演化事件';

CREATE TABLE biz_job_evolution_change (
  job_evolution_change_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  job_evolution_event_id BIGINT UNSIGNED NOT NULL,
  technology_node_id BIGINT UNSIGNED NULL,
  capability_id BIGINT UNSIGNED NULL,
  change_type_code VARCHAR(32) NOT NULL COMMENT 'added/removed/modified',
  change_subtype_code VARCHAR(32) NULL COMMENT 'strengthened/weakened/level/type/other',
  old_value_json JSON NULL,
  new_value_json JSON NULL,
  change_magnitude DECIMAL(7,4) NULL,
  change_reason TEXT NULL,
  evidence_count INT UNSIGNED NOT NULL DEFAULT 0,
  FOREIGN KEY (job_evolution_event_id) REFERENCES biz_job_evolution_event(job_evolution_event_id),
  FOREIGN KEY (technology_node_id) REFERENCES md_technology_node(technology_node_id),
  FOREIGN KEY (capability_id) REFERENCES md_capability(capability_id),
  CHECK ((technology_node_id IS NOT NULL) + (capability_id IS NOT NULL) = 1),
  CHECK (change_type_code IN ('added','removed','modified')),
  KEY idx_evolution_change_event (job_evolution_event_id, change_type_code)
) ENGINE=InnoDB COMMENT='[B/C] 岗位新增、删除和修改的要求项';

-- ============================================================================
-- 7. 周期统计与三类图谱的数据底座
-- ============================================================================

CREATE TABLE biz_analysis_period (
  analysis_period_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  period_code VARCHAR(32) NOT NULL UNIQUE,
  period_type_code VARCHAR(16) NOT NULL COMMENT 'day/week/month/quarter/year/custom',
  start_date DATE NOT NULL,
  end_date DATE NOT NULL,
  is_closed TINYINT(1) NOT NULL DEFAULT 0,
  CHECK (start_date <= end_date)
) ENGINE=InnoDB COMMENT='[B/C] 岗位、能力和算法分析时间窗';

CREATE TABLE mart_job_role_period_metric (
  analysis_period_id BIGINT UNSIGNED NOT NULL,
  job_role_id BIGINT UNSIGNED NOT NULL,
  effective_job_count INT UNSIGNED NOT NULL DEFAULT 0,
  independent_organization_count INT UNSIGNED NOT NULL DEFAULT 0,
  independent_source_count INT UNSIGNED NOT NULL DEFAULT 0,
  active_region_count INT UNSIGNED NOT NULL DEFAULT 0,
  median_salary_monthly DECIMAL(12,2) NULL,
  demand_growth_rate DECIMAL(9,6) NULL,
  capability_change_rate DECIMAL(9,6) NULL,
  data_quality_score DECIMAL(5,2) NULL,
  calculation_version VARCHAR(64) NOT NULL,
  PRIMARY KEY (analysis_period_id, job_role_id),
  FOREIGN KEY (analysis_period_id) REFERENCES biz_analysis_period(analysis_period_id),
  FOREIGN KEY (job_role_id) REFERENCES biz_job_role(job_role_id)
) ENGINE=InnoDB COMMENT='[B] 岗位热度、增长和质量周期指标';

CREATE TABLE mart_role_requirement_period_metric (
  analysis_period_id BIGINT UNSIGNED NOT NULL,
  job_role_id BIGINT UNSIGNED NOT NULL,
  technology_node_id BIGINT UNSIGNED NULL,
  capability_id BIGINT UNSIGNED NULL,
  posting_count INT UNSIGNED NOT NULL DEFAULT 0,
  independent_organization_count INT UNSIGNED NOT NULL DEFAULT 0,
  mention_count INT UNSIGNED NOT NULL DEFAULT 0,
  coverage_rate DECIMAL(9,6) NULL,
  required_ratio DECIMAL(9,6) NULL,
  long_term_importance_score DECIMAL(5,2) NULL,
  recent_activity_score DECIMAL(5,2) NULL,
  growth_rate DECIMAL(9,6) NULL,
  last_seen_at DATETIME NULL,
  trend_code VARCHAR(32) NULL COMMENT 'new/rising/stable/declining/historical',
  calculation_version VARCHAR(64) NOT NULL,
  FOREIGN KEY (analysis_period_id) REFERENCES biz_analysis_period(analysis_period_id),
  FOREIGN KEY (job_role_id) REFERENCES biz_job_role(job_role_id),
  FOREIGN KEY (technology_node_id) REFERENCES md_technology_node(technology_node_id),
  FOREIGN KEY (capability_id) REFERENCES md_capability(capability_id),
  CHECK ((technology_node_id IS NOT NULL) + (capability_id IS NOT NULL) = 1),
  UNIQUE KEY uk_role_period_technology (analysis_period_id, job_role_id, technology_node_id),
  UNIQUE KEY uk_role_period_capability (analysis_period_id, job_role_id, capability_id)
) ENGINE=InnoDB COMMENT='[B] 聚类岗位能力图的长期重要度和近期活跃度';

-- [B] 45天热力图每日触发聚合
CREATE TABLE mart_technology_daily_trigger (
  technology_daily_trigger_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  metric_date DATE NOT NULL,
  technology_domain_id BIGINT UNSIGNED NOT NULL,
  technology_node_id BIGINT UNSIGNED NULL COMMENT '为空时是T域汇总，非空时通常为L2',
  trigger_document_count INT UNSIGNED NOT NULL DEFAULT 0,
  trigger_mention_count INT UNSIGNED NOT NULL DEFAULT 0,
  independent_organization_count INT UNSIGNED NOT NULL DEFAULT 0,
  independent_source_count INT UNSIGNED NOT NULL DEFAULT 0,
  calculation_version VARCHAR(64) NOT NULL,
  technology_scope_key BIGINT UNSIGNED GENERATED ALWAYS AS
    (COALESCE(technology_node_id, 0)) STORED,
  UNIQUE KEY uk_daily_trigger
    (metric_date, technology_domain_id, technology_scope_key, calculation_version),
  FOREIGN KEY (technology_domain_id) REFERENCES md_technology_domain(technology_domain_id),
  FOREIGN KEY (technology_node_id) REFERENCES md_technology_node(technology_node_id),
  KEY idx_daily_trigger_node (technology_node_id, metric_date)
) ENGINE=InnoDB COMMENT='[B] 21x15网格和单T域L2网格的每日触发数';

CREATE TABLE rel_daily_trigger_document (
  metric_date DATE NOT NULL,
  technology_node_id BIGINT UNSIGNED NOT NULL,
  source_document_version_id BIGINT UNSIGNED NOT NULL,
  organization_id BIGINT UNSIGNED NULL,
  evidence_count INT UNSIGNED NOT NULL DEFAULT 1,
  PRIMARY KEY (metric_date, technology_node_id, source_document_version_id),
  FOREIGN KEY (technology_node_id) REFERENCES md_technology_node(technology_node_id),
  FOREIGN KEY (source_document_version_id)
    REFERENCES raw_source_document_version(source_document_version_id),
  FOREIGN KEY (organization_id) REFERENCES md_organization(organization_id)
) ENGINE=InnoDB COMMENT='[B] 点击热力格时回溯当天触发材料';

CREATE TABLE mart_requirement_cooccurrence_metric (
  requirement_cooccurrence_metric_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  analysis_period_id BIGINT UNSIGNED NOT NULL,
  job_role_id BIGINT UNSIGNED NULL COMMENT '为空表示全局',
  capability_a_id BIGINT UNSIGNED NOT NULL,
  capability_b_id BIGINT UNSIGNED NOT NULL,
  cooccurrence_count INT UNSIGNED NOT NULL,
  pmi_score DECIMAL(10,6) NULL,
  lift_score DECIMAL(10,6) NULL,
  relation_strength DECIMAL(7,4) NULL,
  calculation_version VARCHAR(64) NOT NULL,
  role_scope_key BIGINT UNSIGNED GENERATED ALWAYS AS (COALESCE(job_role_id, 0)) STORED,
  UNIQUE KEY uk_requirement_cooccurrence
    (analysis_period_id, role_scope_key, capability_a_id, capability_b_id, calculation_version),
  FOREIGN KEY (analysis_period_id) REFERENCES biz_analysis_period(analysis_period_id),
  FOREIGN KEY (job_role_id) REFERENCES biz_job_role(job_role_id),
  FOREIGN KEY (capability_a_id) REFERENCES md_capability(capability_id),
  FOREIGN KEY (capability_b_id) REFERENCES md_capability(capability_id),
  CHECK (capability_a_id < capability_b_id)
) ENGINE=InnoDB COMMENT='[B] 能力共现边及其时序权重';

-- ============================================================================
-- 8. TETG-EJD v1 新岗位发现、岗位定义和标准JD
-- ============================================================================

-- [C] 自动预测、技术词推演和岗位名称推演统一运行
CREATE TABLE biz_emerging_job_discovery_run (
  discovery_run_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  run_code VARCHAR(64) NOT NULL UNIQUE,
  run_mode_code VARCHAR(32) NOT NULL COMMENT 'auto/technology_directed/name_directed',
  run_name VARCHAR(300) NOT NULL,
  target_date DATE NOT NULL,
  observation_start_date DATE NOT NULL,
  analysis_period_id BIGINT UNSIGNED NULL,
  query_text TEXT NULL COMMENT '岗位名称推演或用户补充描述',
  query_normalized VARCHAR(500) NULL,
  technology_taxonomy_version_id BIGINT UNSIGNED NOT NULL,
  technology_domain_version VARCHAR(32) NOT NULL,
  clustering_run_id BIGINT UNSIGNED NULL,
  algorithm_name VARCHAR(100) NOT NULL DEFAULT 'TETG-EJD',
  algorithm_version VARCHAR(64) NOT NULL,
  algorithm_config_version VARCHAR(64) NOT NULL,
  embedding_model_version VARCHAR(100) NULL,
  llm_model_name VARCHAR(100) NULL,
  prompt_version VARCHAR(64) NULL,
  parameter_json JSON NOT NULL,
  input_job_count INT UNSIGNED NOT NULL DEFAULT 0,
  input_technology_count INT UNSIGNED NOT NULL DEFAULT 0,
  input_milestone_count INT UNSIGNED NOT NULL DEFAULT 0,
  generated_candidate_count INT UNSIGNED NOT NULL DEFAULT 0,
  run_status_code VARCHAR(32) NOT NULL DEFAULT 'pending',
  started_at DATETIME NULL,
  completed_at DATETIME NULL,
  created_by_user_id BIGINT UNSIGNED NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (analysis_period_id) REFERENCES biz_analysis_period(analysis_period_id),
  FOREIGN KEY (technology_taxonomy_version_id)
    REFERENCES md_technology_taxonomy_version(taxonomy_version_id),
  FOREIGN KEY (clustering_run_id) REFERENCES biz_job_clustering_run(clustering_run_id),
  FOREIGN KEY (created_by_user_id) REFERENCES app_user(user_id),
  CHECK (run_mode_code IN ('auto','technology_directed','name_directed')),
  CHECK (run_status_code IN ('pending','running','success','failed','cancelled')),
  CHECK (observation_start_date <= target_date),
  KEY idx_discovery_mode_time (run_mode_code, target_date, run_status_code)
) ENGINE=InnoDB COMMENT='[C] 三种新岗位发现运行及完整输入版本快照';

-- [C] 运行输入统一快照；输入对象仍保留各自主表外键语义
CREATE TABLE rel_discovery_run_input (
  discovery_run_input_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  discovery_run_id BIGINT UNSIGNED NOT NULL,
  input_type_code VARCHAR(32) NOT NULL COMMENT 'job/technology/milestone/role/candidate_technology',
  input_entity_id BIGINT UNSIGNED NOT NULL,
  input_version_text VARCHAR(128) NULL,
  input_hash CHAR(64) NULL,
  input_weight DECIMAL(7,4) NOT NULL DEFAULT 1.0000,
  inclusion_reason_code VARCHAR(32) NOT NULL COMMENT 'window/query/related/manual/recheck',
  snapshot_json JSON NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_discovery_input (discovery_run_id, input_type_code, input_entity_id),
  FOREIGN KEY (discovery_run_id) REFERENCES biz_emerging_job_discovery_run(discovery_run_id),
  CHECK (input_type_code IN ('job','technology','milestone','role','candidate_technology'))
) ENGINE=InnoDB COMMENT='[C] 发现运行实际使用的JD、技术、里程碑和岗位清单';

-- [B/C] 技术在预测截点的成熟度
CREATE TABLE biz_technology_maturity_snapshot (
  maturity_snapshot_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  discovery_run_id BIGINT UNSIGNED NOT NULL,
  technology_node_id BIGINT UNSIGNED NOT NULL,
  target_date DATE NOT NULL,
  maturity_raw DECIMAL(9,8) NOT NULL,
  maturity_explore DECIMAL(9,8) NOT NULL,
  exploration_floor DECIMAL(9,8) NOT NULL,
  relevant_milestone_count INT UNSIGNED NOT NULL DEFAULT 0,
  independent_source_count INT UNSIGNED NOT NULL DEFAULT 0,
  calculation_version VARCHAR(64) NOT NULL,
  UNIQUE KEY uk_maturity_run_technology (discovery_run_id, technology_node_id),
  FOREIGN KEY (discovery_run_id) REFERENCES biz_emerging_job_discovery_run(discovery_run_id),
  FOREIGN KEY (technology_node_id) REFERENCES md_technology_node(technology_node_id),
  CHECK (maturity_raw BETWEEN 0 AND 1),
  CHECK (maturity_explore BETWEEN 0 AND 1)
) ENGINE=InnoDB COMMENT='[B/C] 原始成熟度和仅用于召回的探索成熟度';

CREATE TABLE rel_maturity_milestone_contribution (
  maturity_snapshot_id BIGINT UNSIGNED NOT NULL,
  milestone_event_id BIGINT UNSIGNED NOT NULL,
  event_type_weight DECIMAL(9,8) NOT NULL,
  technology_relevance DECIMAL(9,8) NOT NULL,
  recency_weight DECIMAL(9,8) NOT NULL,
  source_quality_weight DECIMAL(9,8) NOT NULL,
  contribution_score DECIMAL(12,10) NOT NULL,
  rank_no INT UNSIGNED NULL,
  PRIMARY KEY (maturity_snapshot_id, milestone_event_id),
  FOREIGN KEY (maturity_snapshot_id)
    REFERENCES biz_technology_maturity_snapshot(maturity_snapshot_id),
  FOREIGN KEY (milestone_event_id) REFERENCES biz_milestone_event(milestone_event_id)
) ENGINE=InnoDB COMMENT='[B/C] 每条里程碑对技术成熟度的贡献';

-- [B/C] 从模板、真实材料和LLM提出并标准化的产业任务
CREATE TABLE biz_discovery_task (
  discovery_task_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  discovery_run_id BIGINT UNSIGNED NOT NULL,
  task_code VARCHAR(64) NOT NULL,
  task_name VARCHAR(500) NOT NULL,
  normalized_task_name VARCHAR(500) NOT NULL,
  action_verb VARCHAR(100) NULL,
  task_object VARCHAR(500) NULL,
  expected_output VARCHAR(500) NULL,
  task_role_label VARCHAR(32) NULL COMMENT 'data/model/evaluation/planning/deployment/other',
  source_channel_code VARCHAR(32) NOT NULL COMMENT 'template/jd/industry/llm/hybrid',
  technology_relevance_score DECIMAL(5,2) NOT NULL,
  market_support_score DECIMAL(5,2) NOT NULL,
  existing_role_coverage_score DECIMAL(5,2) NOT NULL,
  cross_company_score DECIMAL(5,2) NOT NULL,
  evidence_strength_score DECIMAL(5,2) NOT NULL,
  task_gap_explore_score DECIMAL(5,2) NOT NULL,
  task_gap_publish_score DECIMAL(5,2) NOT NULL,
  task_status_code VARCHAR(32) NOT NULL DEFAULT 'active',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_discovery_task (discovery_run_id, task_code),
  FOREIGN KEY (discovery_run_id) REFERENCES biz_emerging_job_discovery_run(discovery_run_id),
  CHECK (technology_relevance_score BETWEEN 0 AND 100),
  CHECK (market_support_score BETWEEN 0 AND 100),
  CHECK (existing_role_coverage_score BETWEEN 0 AND 100),
  CHECK (task_gap_publish_score BETWEEN 0 AND 100)
) ENGINE=InnoDB COMMENT='[B/C] 技术相关产业任务、市场支撑、岗位覆盖和缺口';

CREATE TABLE rel_discovery_task_evidence (
  discovery_task_id BIGINT UNSIGNED NOT NULL,
  evidence_span_id BIGINT UNSIGNED NOT NULL,
  evidence_role_code VARCHAR(32) NOT NULL COMMENT 'task/technology/market/application/contradiction',
  support_type_code VARCHAR(32) NOT NULL DEFAULT 'support',
  support_score DECIMAL(5,2) NOT NULL,
  source_organization_id BIGINT UNSIGNED NULL,
  PRIMARY KEY (discovery_task_id, evidence_span_id, evidence_role_code),
  FOREIGN KEY (discovery_task_id) REFERENCES biz_discovery_task(discovery_task_id),
  FOREIGN KEY (evidence_span_id) REFERENCES biz_evidence_span(evidence_span_id),
  FOREIGN KEY (source_organization_id) REFERENCES md_organization(organization_id),
  CHECK (support_type_code IN ('support','contradict'))
) ENGINE=InnoDB COMMENT='[B/C] 产业任务对应的JD和应用原文证据';

-- [B/C] 算法候选岗位；成熟阶段与审核状态严格分离
CREATE TABLE biz_emerging_job_candidate (
  emerging_job_candidate_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  candidate_code VARCHAR(64) NOT NULL UNIQUE,
  candidate_group_code VARCHAR(64) NOT NULL,
  candidate_version_no INT UNSIGNED NOT NULL DEFAULT 1,
  previous_candidate_id BIGINT UNSIGNED NULL,
  discovery_run_id BIGINT UNSIGNED NOT NULL,
  candidate_name VARCHAR(300) NOT NULL,
  normalized_name VARCHAR(300) NOT NULL,
  candidate_stage_code VARCHAR(32) NOT NULL COMMENT 'potential/budding/emerging/confirmed',
  workflow_status_code VARCHAR(32) NOT NULL DEFAULT 'pending',
  one_line_definition TEXT NULL,
  core_responsibility_text LONGTEXT NULL,
  formation_reason_text LONGTEXT NULL,
  expected_formation_window VARCHAR(100) NULL,
  mechanical_snapshot_json JSON NOT NULL,
  llm_output_json JSON NULL,
  supporting_job_count INT UNSIGNED NOT NULL DEFAULT 0,
  independent_organization_count INT UNSIGNED NOT NULL DEFAULT 0,
  independent_source_count INT UNSIGNED NOT NULL DEFAULT 0,
  observation_window_count INT UNSIGNED NOT NULL DEFAULT 0,
  candidate_score DECIMAL(5,2) NOT NULL,
  hallucination_risk_score DECIMAL(5,2) NOT NULL DEFAULT 0,
  approved_job_role_id BIGINT UNSIGNED NULL,
  duplicate_of_job_role_id BIGINT UNSIGNED NULL,
  review_reason TEXT NULL,
  reviewed_at DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_candidate_group_version (candidate_group_code, candidate_version_no),
  FOREIGN KEY (previous_candidate_id) REFERENCES biz_emerging_job_candidate(emerging_job_candidate_id),
  FOREIGN KEY (discovery_run_id) REFERENCES biz_emerging_job_discovery_run(discovery_run_id),
  FOREIGN KEY (approved_job_role_id) REFERENCES biz_job_role(job_role_id),
  FOREIGN KEY (duplicate_of_job_role_id) REFERENCES biz_job_role(job_role_id),
  CHECK (candidate_stage_code IN ('potential','budding','emerging','confirmed')),
  CHECK (workflow_status_code IN ('pending','reviewing','needs_revision','approved','rejected','merged')),
  CHECK (candidate_score BETWEEN 0 AND 100),
  KEY idx_candidate_review (workflow_status_code, candidate_stage_code, candidate_score)
) ENGINE=InnoDB COMMENT='[B/C] 新岗位候选、成熟阶段、机械事实和LLM表达';

CREATE TABLE rel_emerging_candidate_task (
  emerging_job_candidate_id BIGINT UNSIGNED NOT NULL,
  discovery_task_id BIGINT UNSIGNED NOT NULL,
  task_role_code VARCHAR(32) NOT NULL COMMENT 'core/supporting',
  community_id VARCHAR(64) NULL,
  community_cohesion_score DECIMAL(5,2) NULL,
  task_weight DECIMAL(7,4) NOT NULL,
  PRIMARY KEY (emerging_job_candidate_id, discovery_task_id),
  FOREIGN KEY (emerging_job_candidate_id)
    REFERENCES biz_emerging_job_candidate(emerging_job_candidate_id),
  FOREIGN KEY (discovery_task_id) REFERENCES biz_discovery_task(discovery_task_id)
) ENGINE=InnoDB COMMENT='[B/C] 候选岗位的任务社区和核心/配套任务';

CREATE TABLE rel_emerging_candidate_requirement (
  candidate_requirement_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  emerging_job_candidate_id BIGINT UNSIGNED NOT NULL,
  technology_node_id BIGINT UNSIGNED NULL,
  capability_id BIGINT UNSIGNED NULL,
  requirement_type_code VARCHAR(32) NOT NULL COMMENT 'required/bonus/frontier',
  required_level_code VARCHAR(32) NULL,
  importance_score DECIMAL(5,2) NOT NULL,
  confidence_score DECIMAL(5,2) NOT NULL,
  supporting_job_count INT UNSIGNED NOT NULL DEFAULT 0,
  independent_organization_count INT UNSIGNED NOT NULL DEFAULT 0,
  is_human_edited TINYINT(1) NOT NULL DEFAULT 0,
  FOREIGN KEY (emerging_job_candidate_id)
    REFERENCES biz_emerging_job_candidate(emerging_job_candidate_id),
  FOREIGN KEY (technology_node_id) REFERENCES md_technology_node(technology_node_id),
  FOREIGN KEY (capability_id) REFERENCES md_capability(capability_id),
  CHECK ((technology_node_id IS NOT NULL) + (capability_id IS NOT NULL) = 1),
  CHECK (requirement_type_code IN ('required','bonus','frontier')),
  CHECK (importance_score BETWEEN 0 AND 100),
  CHECK (confidence_score BETWEEN 0 AND 100),
  UNIQUE KEY uk_candidate_technology_requirement
    (emerging_job_candidate_id, technology_node_id, requirement_type_code),
  UNIQUE KEY uk_candidate_capability_requirement
    (emerging_job_candidate_id, capability_id, requirement_type_code)
) ENGINE=InnoDB COMMENT='[B/C] 候选岗位的必需、加分和前沿要求';

CREATE TABLE rel_emerging_candidate_domain (
  emerging_job_candidate_id BIGINT UNSIGNED NOT NULL,
  technology_domain_id BIGINT UNSIGNED NOT NULL,
  domain_score DECIMAL(5,2) NOT NULL,
  is_primary TINYINT(1) NOT NULL DEFAULT 0,
  PRIMARY KEY (emerging_job_candidate_id, technology_domain_id),
  FOREIGN KEY (emerging_job_candidate_id)
    REFERENCES biz_emerging_job_candidate(emerging_job_candidate_id),
  FOREIGN KEY (technology_domain_id) REFERENCES md_technology_domain(technology_domain_id)
) ENGINE=InnoDB COMMENT='[B/C] 候选岗位的T1-T7领域分布';

-- [B/C] 候选岗位与已有正式岗位的多维比较
CREATE TABLE rel_emerging_candidate_nearest_role (
  emerging_job_candidate_id BIGINT UNSIGNED NOT NULL,
  job_role_version_id BIGINT UNSIGNED NOT NULL,
  rank_no INT UNSIGNED NOT NULL,
  title_similarity DECIMAL(7,6) NOT NULL,
  responsibility_similarity DECIMAL(7,6) NOT NULL,
  requirement_similarity DECIMAL(7,6) NOT NULL,
  scenario_similarity DECIMAL(7,6) NOT NULL,
  level_similarity DECIMAL(7,6) NOT NULL,
  overall_overlap_score DECIMAL(7,6) NOT NULL,
  difference_summary TEXT NULL,
  PRIMARY KEY (emerging_job_candidate_id, job_role_version_id),
  FOREIGN KEY (emerging_job_candidate_id)
    REFERENCES biz_emerging_job_candidate(emerging_job_candidate_id),
  FOREIGN KEY (job_role_version_id) REFERENCES biz_job_role_version(job_role_version_id),
  KEY idx_candidate_nearest_rank (emerging_job_candidate_id, rank_no)
) ENGINE=InnoDB COMMENT='[B/C] 候选与已有岗位的名称、职责、要求和场景重合';

-- [B/C] 八维正向分和各类惩罚项
CREATE TABLE biz_emerging_candidate_score (
  emerging_candidate_score_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  emerging_job_candidate_id BIGINT UNSIGNED NOT NULL,
  dimension_code VARCHAR(64) NOT NULL,
  raw_score DECIMAL(7,4) NOT NULL,
  weight_value DECIMAL(9,8) NOT NULL DEFAULT 0,
  contribution_score DECIMAL(7,4) NOT NULL,
  score_type_code VARCHAR(16) NOT NULL COMMENT 'positive/penalty/gate',
  calculation_detail_json JSON NULL,
  UNIQUE KEY uk_candidate_score_dimension (emerging_job_candidate_id, dimension_code),
  FOREIGN KEY (emerging_job_candidate_id)
    REFERENCES biz_emerging_job_candidate(emerging_job_candidate_id),
  CHECK (score_type_code IN ('positive','penalty','gate'))
) ENGINE=InnoDB COMMENT='[B/C] 技术、缺口、凝聚、市场、成熟度、趋势、证据、新颖性和惩罚';

CREATE TABLE rel_emerging_candidate_evidence (
  emerging_job_candidate_id BIGINT UNSIGNED NOT NULL,
  evidence_span_id BIGINT UNSIGNED NOT NULL,
  evidence_role_code VARCHAR(32) NOT NULL
    COMMENT 'name/definition/responsibility/requirement/scenario/novelty/market',
  support_type_code VARCHAR(32) NOT NULL DEFAULT 'support',
  support_score DECIMAL(5,2) NOT NULL,
  explanation_text TEXT NULL,
  PRIMARY KEY (emerging_job_candidate_id, evidence_span_id, evidence_role_code),
  FOREIGN KEY (emerging_job_candidate_id)
    REFERENCES biz_emerging_job_candidate(emerging_job_candidate_id),
  FOREIGN KEY (evidence_span_id) REFERENCES biz_evidence_span(evidence_span_id),
  CHECK (support_type_code IN ('support','contradict'))
) ENGINE=InnoDB COMMENT='[B/C] 候选岗位名称、职责、要求、场景和市场证据';

-- [C] 标准JD与真实招聘JD物理隔离
CREATE TABLE biz_generated_job_description (
  generated_job_description_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  generated_jd_code VARCHAR(64) NOT NULL UNIQUE,
  job_role_version_id BIGINT UNSIGNED NOT NULL,
  source_candidate_id BIGINT UNSIGNED NULL,
  generation_context_json JSON NOT NULL
    COMMENT '企业类型、级别、地点、学历、经验、团队目标',
  generated_jd_status_code VARCHAR(32) NOT NULL DEFAULT 'draft',
  created_by_user_id BIGINT UNSIGNED NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (job_role_version_id) REFERENCES biz_job_role_version(job_role_version_id),
  FOREIGN KEY (source_candidate_id)
    REFERENCES biz_emerging_job_candidate(emerging_job_candidate_id),
  FOREIGN KEY (created_by_user_id) REFERENCES app_user(user_id),
  CHECK (generated_jd_status_code IN ('draft','reviewing','approved','retired'))
) ENGINE=InnoDB COMMENT='[C] 参考标准JD的稳定实体，绝不计入真实招聘统计';

CREATE TABLE biz_generated_job_description_version (
  generated_jd_version_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  generated_job_description_id BIGINT UNSIGNED NOT NULL,
  version_no INT UNSIGNED NOT NULL,
  previous_version_id BIGINT UNSIGNED NULL,
  content_text LONGTEXT NOT NULL,
  content_json JSON NOT NULL,
  edit_source_code VARCHAR(32) NOT NULL COMMENT 'llm/human/hybrid',
  model_name VARCHAR(100) NULL,
  prompt_version VARCHAR(64) NULL,
  approved_by_user_id BIGINT UNSIGNED NULL,
  approved_at DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_generated_jd_version (generated_job_description_id, version_no),
  FOREIGN KEY (generated_job_description_id)
    REFERENCES biz_generated_job_description(generated_job_description_id),
  FOREIGN KEY (previous_version_id)
    REFERENCES biz_generated_job_description_version(generated_jd_version_id),
  FOREIGN KEY (approved_by_user_id) REFERENCES app_user(user_id)
) ENGINE=InnoDB COMMENT='[C] 标准JD的模型生成、人工修订和审批版本';

-- ============================================================================
-- 9. 简历、对话式画像、人岗匹配和发展路径
-- ============================================================================

-- [A/C] 上传、粘贴或OCR后的简历文本版本
CREATE TABLE biz_resume (
  resume_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  resume_code VARCHAR(64) NOT NULL UNIQUE,
  resume_group_code VARCHAR(64) NOT NULL,
  version_no INT UNSIGNED NOT NULL,
  previous_resume_id BIGINT UNSIGNED NULL,
  owner_user_id BIGINT UNSIGNED NOT NULL,
  source_document_version_id BIGINT UNSIGNED NULL,
  file_asset_id BIGINT UNSIGNED NULL,
  resume_name VARCHAR(300) NULL,
  input_type_code VARCHAR(32) NOT NULL COMMENT 'pdf/docx/txt/image/text',
  content_text LONGTEXT NOT NULL,
  content_hash CHAR(64) NOT NULL,
  consent_status_code VARCHAR(32) NOT NULL DEFAULT 'temporary',
  expires_at DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_resume_group_version (resume_group_code, version_no),
  FOREIGN KEY (previous_resume_id) REFERENCES biz_resume(resume_id),
  FOREIGN KEY (owner_user_id) REFERENCES app_user(user_id),
  FOREIGN KEY (source_document_version_id)
    REFERENCES raw_source_document_version(source_document_version_id),
  FOREIGN KEY (file_asset_id) REFERENCES raw_file_asset(file_asset_id),
  CHECK (consent_status_code IN ('temporary','granted','withdrawn','expired','deleted'))
) ENGINE=InnoDB COMMENT='[A/C] 简历原文件、提取文本及其版本';

-- [C] 稳定画像实体
CREATE TABLE biz_candidate_profile (
  candidate_profile_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  profile_code VARCHAR(64) NOT NULL UNIQUE,
  owner_user_id BIGINT UNSIGNED NOT NULL,
  profile_name VARCHAR(300) NOT NULL,
  profile_status_code VARCHAR(32) NOT NULL DEFAULT 'active',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  FOREIGN KEY (owner_user_id) REFERENCES app_user(user_id),
  CHECK (profile_status_code IN ('active','archived','deleted'))
) ENGINE=InnoDB COMMENT='[C] 用户可选择和管理的稳定求职者画像';

-- [C] 画像事实、洞察、经历和偏好快照
CREATE TABLE biz_candidate_profile_version (
  candidate_profile_version_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  candidate_profile_id BIGINT UNSIGNED NOT NULL,
  version_no INT UNSIGNED NOT NULL,
  previous_version_id BIGINT UNSIGNED NULL,
  resume_id BIGINT UNSIGNED NOT NULL,
  version_status_code VARCHAR(32) NOT NULL DEFAULT 'draft',
  current_profile_guard BIGINT UNSIGNED GENERATED ALWAYS AS
    (CASE WHEN version_status_code = 'confirmed'
      THEN candidate_profile_id ELSE NULL END) STORED,
  target_role_text VARCHAR(500) NULL,
  target_job_level_code VARCHAR(32) NULL,
  basic_fact_json JSON NOT NULL,
  education_json JSON NULL,
  experience_json JSON NULL,
  project_json JSON NULL,
  achievement_json JSON NULL,
  insight_json JSON NULL,
  preference_json JSON NULL,
  source_summary_json JSON NULL,
  model_name VARCHAR(100) NULL,
  prompt_version VARCHAR(64) NULL,
  user_confirmed_at DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_profile_version (candidate_profile_id, version_no),
  UNIQUE KEY uk_profile_one_confirmed (current_profile_guard),
  FOREIGN KEY (candidate_profile_id) REFERENCES biz_candidate_profile(candidate_profile_id),
  FOREIGN KEY (previous_version_id)
    REFERENCES biz_candidate_profile_version(candidate_profile_version_id),
  FOREIGN KEY (resume_id) REFERENCES biz_resume(resume_id),
  CHECK (version_status_code IN ('draft','questioning','confirmed','superseded'))
) ENGINE=InnoDB COMMENT='[C] 可追溯的事实层、洞察层、经历和偏好画像版本';

CREATE TABLE rel_profile_version_capability (
  profile_capability_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  candidate_profile_version_id BIGINT UNSIGNED NOT NULL,
  capability_id BIGINT UNSIGNED NOT NULL,
  proficiency_level_code VARCHAR(32) NULL,
  proficiency_score DECIMAL(5,2) NULL,
  evidence_level_code VARCHAR(32) NULL,
  months_of_use INT UNSIGNED NULL,
  last_used_at DATE NULL,
  confidence_score DECIMAL(5,2) NOT NULL,
  fact_source_code VARCHAR(32) NOT NULL COMMENT 'resume/user_answer/system_inference/user_confirmed',
  is_user_confirmed TINYINT(1) NOT NULL DEFAULT 0,
  evidence_json JSON NULL,
  UNIQUE KEY uk_profile_capability (candidate_profile_version_id, capability_id),
  FOREIGN KEY (candidate_profile_version_id)
    REFERENCES biz_candidate_profile_version(candidate_profile_version_id),
  FOREIGN KEY (capability_id) REFERENCES md_capability(capability_id),
  CHECK (proficiency_score IS NULL OR proficiency_score BETWEEN 0 AND 100),
  CHECK (confidence_score BETWEEN 0 AND 100)
) ENGINE=InnoDB COMMENT='[C] 画像版本的能力、熟练度、时长、新鲜度和证据';

CREATE TABLE biz_profile_conversation (
  profile_conversation_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  conversation_code VARCHAR(64) NOT NULL UNIQUE,
  candidate_profile_id BIGINT UNSIGNED NOT NULL,
  base_resume_id BIGINT UNSIGNED NOT NULL,
  conversation_status_code VARCHAR(32) NOT NULL DEFAULT 'active',
  min_question_count TINYINT UNSIGNED NOT NULL DEFAULT 2,
  max_question_count TINYINT UNSIGNED NOT NULL DEFAULT 8,
  completed_reason_code VARCHAR(32) NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  completed_at DATETIME NULL,
  FOREIGN KEY (candidate_profile_id) REFERENCES biz_candidate_profile(candidate_profile_id),
  FOREIGN KEY (base_resume_id) REFERENCES biz_resume(resume_id),
  CHECK (max_question_count BETWEEN 2 AND 8),
  CHECK (min_question_count <= max_question_count)
) ENGINE=InnoDB COMMENT='[C] 简历上传后的2-8轮自适应建档会话';

CREATE TABLE biz_profile_message (
  profile_message_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  profile_conversation_id BIGINT UNSIGNED NOT NULL,
  sequence_no INT UNSIGNED NOT NULL,
  message_role_code VARCHAR(16) NOT NULL COMMENT 'system/assistant/user',
  message_type_code VARCHAR(32) NOT NULL COMMENT 'question/answer/notice/file/summary',
  content_text LONGTEXT NOT NULL,
  structured_content_json JSON NULL,
  question_dimension_code VARCHAR(64) NULL,
  question_value_score DECIMAL(5,2) NULL,
  evidence_ids_json JSON NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_profile_message_sequence (profile_conversation_id, sequence_no),
  FOREIGN KEY (profile_conversation_id)
    REFERENCES biz_profile_conversation(profile_conversation_id)
) ENGINE=InnoDB COMMENT='[C] 建档问题、回答、上传和最终总结';

-- [C] 一次画像版本到岗位/JD的匹配运行
CREATE TABLE biz_match_run (
  match_run_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  run_code VARCHAR(64) NOT NULL UNIQUE,
  candidate_profile_version_id BIGINT UNSIGNED NOT NULL,
  target_type_code VARCHAR(32) NOT NULL COMMENT 'job_role_version/job_posting/search',
  target_id BIGINT UNSIGNED NULL,
  algorithm_version VARCHAR(64) NOT NULL,
  capability_ontology_version VARCHAR(32) NOT NULL,
  filter_json JSON NULL,
  weight_json JSON NOT NULL,
  input_snapshot_json JSON NOT NULL,
  run_status_code VARCHAR(32) NOT NULL DEFAULT 'pending',
  started_at DATETIME NULL,
  completed_at DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (candidate_profile_version_id)
    REFERENCES biz_candidate_profile_version(candidate_profile_version_id),
  CHECK (target_type_code IN ('job_role_version','job_posting','search')),
  CHECK (run_status_code IN ('pending','running','success','failed','cancelled'))
) ENGINE=InnoDB COMMENT='[C] 冻结画像版本、目标版本、权重和算法的一次匹配';

CREATE TABLE biz_match_result (
  match_result_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  match_run_id BIGINT UNSIGNED NOT NULL,
  job_role_version_id BIGINT UNSIGNED NULL,
  job_posting_id BIGINT UNSIGNED NULL,
  rank_no INT UNSIGNED NULL,
  total_score DECIMAL(5,2) NOT NULL,
  confidence_score DECIMAL(5,2) NOT NULL,
  matched_requirement_count INT UNSIGNED NOT NULL DEFAULT 0,
  missing_requirement_count INT UNSIGNED NOT NULL DEFAULT 0,
  evidence_insufficient_count INT UNSIGNED NOT NULL DEFAULT 0,
  mechanical_explanation_json JSON NOT NULL,
  llm_explanation_text LONGTEXT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (match_run_id) REFERENCES biz_match_run(match_run_id),
  FOREIGN KEY (job_role_version_id) REFERENCES biz_job_role_version(job_role_version_id),
  FOREIGN KEY (job_posting_id) REFERENCES biz_job_posting(job_posting_id),
  CHECK ((job_role_version_id IS NOT NULL) + (job_posting_id IS NOT NULL) = 1),
  CHECK (total_score BETWEEN 0 AND 100),
  UNIQUE KEY uk_match_role_result (match_run_id, job_role_version_id),
  UNIQUE KEY uk_match_job_result (match_run_id, job_posting_id),
  KEY idx_match_rank (match_run_id, rank_no, total_score)
) ENGINE=InnoDB COMMENT='[C] 岗位卡片排名、机械解释和LLM说明';

CREATE TABLE biz_match_dimension_result (
  match_result_id BIGINT UNSIGNED NOT NULL,
  dimension_code VARCHAR(64) NOT NULL,
  raw_score DECIMAL(5,2) NOT NULL,
  weight_value DECIMAL(9,8) NOT NULL,
  contribution_score DECIMAL(7,4) NOT NULL,
  confidence_score DECIMAL(5,2) NULL,
  explanation_text TEXT NULL,
  PRIMARY KEY (match_result_id, dimension_code),
  FOREIGN KEY (match_result_id) REFERENCES biz_match_result(match_result_id)
) ENGINE=InnoDB COMMENT='[C] 必需能力、深度、任务、项目、时效、场景、级别、迁移和偏好分';

CREATE TABLE biz_match_requirement_detail (
  match_requirement_detail_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  match_result_id BIGINT UNSIGNED NOT NULL,
  role_version_requirement_id BIGINT UNSIGNED NULL,
  job_requirement_id BIGINT UNSIGNED NULL,
  capability_id BIGINT UNSIGNED NULL,
  required_level_score DECIMAL(5,2) NULL,
  actual_level_score DECIMAL(5,2) NULL,
  gap_score DECIMAL(7,4) NULL,
  contribution_score DECIMAL(7,4) NULL,
  gap_type_code VARCHAR(32) NOT NULL
    COMMENT 'met/confirmed_missing/evidence_insufficient/depth_insufficient/transferable/requirement_uncertain',
  candidate_evidence_json JSON NULL,
  job_evidence_json JSON NULL,
  FOREIGN KEY (match_result_id) REFERENCES biz_match_result(match_result_id),
  FOREIGN KEY (role_version_requirement_id)
    REFERENCES rel_job_role_version_requirement(role_version_requirement_id),
  FOREIGN KEY (job_requirement_id) REFERENCES biz_job_requirement(job_requirement_id),
  FOREIGN KEY (capability_id) REFERENCES md_capability(capability_id),
  CHECK ((role_version_requirement_id IS NOT NULL) + (job_requirement_id IS NOT NULL) = 1),
  KEY idx_match_gap (match_result_id, gap_type_code, gap_score)
) ENGINE=InnoDB COMMENT='[C] 逐要求差距、双方证据和可迁移判断';

-- [A/C] 学习资源可来自外部基础数据，也可由管理员维护
CREATE TABLE md_learning_resource (
  learning_resource_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  resource_code VARCHAR(64) NOT NULL UNIQUE,
  resource_type_code VARCHAR(32) NOT NULL COMMENT 'course/book/project/certificate/document',
  resource_name VARCHAR(500) NOT NULL,
  provider_name VARCHAR(300) NULL,
  resource_url VARCHAR(1500) NULL,
  difficulty_level_code VARCHAR(32) NULL,
  estimated_hours DECIMAL(8,2) NULL,
  quality_score DECIMAL(5,2) NULL,
  capability_coverage_json JSON NULL,
  is_active TINYINT(1) NOT NULL DEFAULT 1
) ENGINE=InnoDB COMMENT='[A/C] 差距补齐所需课程、项目、证书和资料';

CREATE TABLE biz_learning_path (
  learning_path_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  path_code VARCHAR(64) NOT NULL UNIQUE,
  match_result_id BIGINT UNSIGNED NOT NULL,
  path_version_no INT UNSIGNED NOT NULL DEFAULT 1,
  path_name VARCHAR(500) NOT NULL,
  algorithm_version VARCHAR(64) NOT NULL,
  model_name VARCHAR(100) NULL,
  prompt_version VARCHAR(64) NULL,
  total_estimated_hours DECIMAL(10,2) NULL,
  target_completion_date DATE NULL,
  path_status_code VARCHAR(32) NOT NULL DEFAULT 'proposed',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (match_result_id) REFERENCES biz_match_result(match_result_id)
) ENGINE=InnoDB COMMENT='[C] 绑定具体匹配差距的发展路径版本';

CREATE TABLE biz_learning_path_step (
  learning_path_step_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  learning_path_id BIGINT UNSIGNED NOT NULL,
  step_no INT UNSIGNED NOT NULL,
  capability_id BIGINT UNSIGNED NOT NULL,
  learning_resource_id BIGINT UNSIGNED NULL,
  current_level_score DECIMAL(5,2) NULL,
  target_level_score DECIMAL(5,2) NULL,
  action_text TEXT NOT NULL,
  practice_task_text TEXT NOT NULL,
  verification_standard_text TEXT NOT NULL,
  estimated_hours DECIMAL(8,2) NULL,
  priority_code VARCHAR(16) NOT NULL,
  expected_match_improvement_json JSON NULL,
  completion_status_code VARCHAR(32) NOT NULL DEFAULT 'not_started',
  UNIQUE KEY uk_learning_step_no (learning_path_id, step_no),
  FOREIGN KEY (learning_path_id) REFERENCES biz_learning_path(learning_path_id),
  FOREIGN KEY (capability_id) REFERENCES md_capability(capability_id),
  FOREIGN KEY (learning_resource_id) REFERENCES md_learning_resource(learning_resource_id)
) ENGINE=InnoDB COMMENT='[C] 差距、前置能力、实践任务和验证标准';

CREATE TABLE rel_learning_step_dependency (
  learning_path_step_id BIGINT UNSIGNED NOT NULL,
  prerequisite_step_id BIGINT UNSIGNED NOT NULL,
  dependency_type_code VARCHAR(32) NOT NULL DEFAULT 'required',
  PRIMARY KEY (learning_path_step_id, prerequisite_step_id),
  FOREIGN KEY (learning_path_step_id) REFERENCES biz_learning_path_step(learning_path_step_id),
  FOREIGN KEY (prerequisite_step_id) REFERENCES biz_learning_path_step(learning_path_step_id),
  CHECK (learning_path_step_id <> prerequisite_step_id),
  CHECK (dependency_type_code IN ('required','recommended'))
) ENGINE=InnoDB COMMENT='[C] 学习步骤多对多前置依赖';

-- ============================================================================
-- 10. 基准数据、量化评测和消融实验
-- ============================================================================

CREATE TABLE biz_benchmark_dataset (
  benchmark_dataset_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  dataset_code VARCHAR(64) NOT NULL UNIQUE,
  dataset_name VARCHAR(300) NOT NULL,
  dataset_type_code VARCHAR(32) NOT NULL
    COMMENT 'jd_parse/resume_parse/match/emerging_job/time_backtest/mixed',
  version_code VARCHAR(32) NOT NULL,
  description_text TEXT NULL,
  sample_count INT UNSIGNED NOT NULL DEFAULT 0,
  jd_sample_count INT UNSIGNED NOT NULL DEFAULT 0,
  annotation_guideline_version VARCHAR(64) NULL,
  split_strategy_code VARCHAR(32) NULL,
  is_frozen TINYINT(1) NOT NULL DEFAULT 0,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_benchmark_version (dataset_name, version_code)
) ENGINE=InnoDB COMMENT='[C] 100条以上JD及解析、匹配和新岗位评测集';

CREATE TABLE biz_test_case (
  test_case_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  benchmark_dataset_id BIGINT UNSIGNED NOT NULL,
  case_code VARCHAR(64) NOT NULL,
  task_type_code VARCHAR(32) NOT NULL
    COMMENT 'jd_parse/resume_parse/match/emerging_job/time_backtest',
  input_json JSON NOT NULL,
  expected_json JSON NOT NULL,
  annotation_status_code VARCHAR(32) NOT NULL DEFAULT 'draft',
  annotated_by VARCHAR(100) NULL,
  reviewed_by VARCHAR(100) NULL,
  difficulty_code VARCHAR(32) NULL,
  UNIQUE KEY uk_test_case (benchmark_dataset_id, case_code),
  FOREIGN KEY (benchmark_dataset_id) REFERENCES biz_benchmark_dataset(benchmark_dataset_id)
) ENGINE=InnoDB COMMENT='[C] 测试输入和人工金标准';

CREATE TABLE biz_evaluation_run (
  evaluation_run_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  evaluation_code VARCHAR(64) NOT NULL UNIQUE,
  benchmark_dataset_id BIGINT UNSIGNED NOT NULL,
  experiment_type_code VARCHAR(32) NOT NULL COMMENT 'default/baseline/ablation/time_backtest',
  experiment_name VARCHAR(200) NOT NULL,
  system_version VARCHAR(64) NOT NULL,
  algorithm_version VARCHAR(64) NULL,
  algorithm_config_version VARCHAR(64) NULL,
  model_name VARCHAR(100) NULL,
  prompt_version VARCHAR(64) NULL,
  environment_json JSON NULL,
  run_status_code VARCHAR(32) NOT NULL DEFAULT 'pending',
  started_at DATETIME NULL,
  completed_at DATETIME NULL,
  FOREIGN KEY (benchmark_dataset_id) REFERENCES biz_benchmark_dataset(benchmark_dataset_id),
  CHECK (experiment_type_code IN ('default','baseline','ablation','time_backtest')),
  CHECK (run_status_code IN ('pending','running','success','failed','cancelled'))
) ENGINE=InnoDB COMMENT='[C] 官方指标、基线、消融和时间回测运行';

CREATE TABLE biz_evaluation_item (
  evaluation_run_id BIGINT UNSIGNED NOT NULL,
  test_case_id BIGINT UNSIGNED NOT NULL,
  predicted_json JSON NULL,
  is_correct TINYINT(1) NULL,
  score DECIMAL(9,8) NULL,
  latency_ms INT UNSIGNED NULL,
  error_type_code VARCHAR(64) NULL,
  error_detail TEXT NULL,
  PRIMARY KEY (evaluation_run_id, test_case_id),
  FOREIGN KEY (evaluation_run_id) REFERENCES biz_evaluation_run(evaluation_run_id),
  FOREIGN KEY (test_case_id) REFERENCES biz_test_case(test_case_id),
  CHECK (score IS NULL OR score BETWEEN 0 AND 1)
) ENGINE=InnoDB COMMENT='[C] 每个测试用例的预测和错误类型';

CREATE TABLE biz_evaluation_metric (
  evaluation_run_id BIGINT UNSIGNED NOT NULL,
  task_type_code VARCHAR(32) NOT NULL,
  metric_name VARCHAR(64) NOT NULL
    COMMENT 'accuracy/precision/recall/f1/ndcg/coverage/latency/hallucination_rate',
  metric_value DECIMAL(12,8) NOT NULL,
  sample_count INT UNSIGNED NOT NULL,
  threshold_value DECIMAL(12,8) NULL,
  passed TINYINT(1) NULL,
  computed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (evaluation_run_id, task_type_code, metric_name),
  FOREIGN KEY (evaluation_run_id) REFERENCES biz_evaluation_run(evaluation_run_id)
) ENGINE=InnoDB COMMENT='[C] 三项90%指标和新岗位研究指标';

-- ============================================================================
-- 11. 事务一致性、幂等和审计
-- ============================================================================

CREATE TABLE sys_algorithm_config (
  algorithm_config_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  algorithm_name VARCHAR(100) NOT NULL,
  config_version VARCHAR(64) NOT NULL,
  config_json JSON NOT NULL COMMENT '权重、阈值、衰减、硬门槛和消融开关',
  config_hash CHAR(64) NOT NULL,
  config_status_code VARCHAR(32) NOT NULL DEFAULT 'draft',
  effective_from DATETIME NULL,
  created_by_user_id BIGINT UNSIGNED NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_algorithm_config (algorithm_name, config_version),
  FOREIGN KEY (created_by_user_id) REFERENCES app_user(user_id),
  CHECK (config_status_code IN ('draft','active','retired'))
) ENGINE=InnoDB COMMENT='[C] TETG-EJD、聚类、匹配和质量算法配置版本';

CREATE TABLE sys_async_task (
  async_task_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  task_code VARCHAR(64) NOT NULL UNIQUE,
  task_type_code VARCHAR(64) NOT NULL,
  target_type_code VARCHAR(64) NULL,
  target_id BIGINT UNSIGNED NULL,
  idempotency_key VARCHAR(128) NOT NULL,
  input_snapshot_json JSON NOT NULL,
  task_status_code VARCHAR(32) NOT NULL DEFAULT 'pending',
  attempt_count INT UNSIGNED NOT NULL DEFAULT 0,
  max_attempt_count INT UNSIGNED NOT NULL DEFAULT 3,
  available_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  started_at DATETIME NULL,
  completed_at DATETIME NULL,
  last_error_code VARCHAR(64) NULL,
  last_error_message TEXT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_async_task_idempotency (task_type_code, idempotency_key),
  CHECK (task_status_code IN ('pending','running','success','failed','cancelled','dead_letter')),
  KEY idx_async_task_queue (task_status_code, available_at, async_task_id)
) ENGINE=InnoDB COMMENT='[C] 采集、OCR、抽取、聚类、推演、匹配和评测任务';

CREATE TABLE sys_idempotency_record (
  idempotency_key VARCHAR(128) PRIMARY KEY,
  operation_code VARCHAR(64) NOT NULL,
  request_hash CHAR(64) NOT NULL,
  response_status_code INT NULL,
  response_json JSON NULL,
  record_status_code VARCHAR(32) NOT NULL DEFAULT 'processing',
  expires_at DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB COMMENT='[C] 写接口和异步任务防重复';

CREATE TABLE sys_outbox_event (
  outbox_event_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  aggregate_type_code VARCHAR(64) NOT NULL,
  aggregate_id BIGINT UNSIGNED NOT NULL,
  event_type_code VARCHAR(100) NOT NULL,
  event_payload_json JSON NOT NULL,
  event_status_code VARCHAR(32) NOT NULL DEFAULT 'pending',
  attempt_count INT UNSIGNED NOT NULL DEFAULT 0,
  available_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  published_at DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY idx_outbox_pending (event_status_code, available_at, outbox_event_id)
) ENGINE=InnoDB COMMENT='[C] 数据库提交后刷新图谱、搜索和缓存的事务Outbox';

CREATE TABLE sys_audit_log (
  audit_log_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  actor_user_id BIGINT UNSIGNED NULL,
  action_code VARCHAR(64) NOT NULL,
  target_type_code VARCHAR(64) NOT NULL,
  target_id BIGINT UNSIGNED NOT NULL,
  before_json JSON NULL,
  after_json JSON NULL,
  trace_id VARCHAR(128) NULL,
  acted_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (actor_user_id) REFERENCES app_user(user_id),
  KEY idx_audit_target (target_type_code, target_id, acted_at),
  KEY idx_audit_actor (actor_user_id, acted_at)
) ENGINE=InnoDB COMMENT='[C] 数据、岗位、画像和匹配关键操作审计';

-- [C] 简历处理、画像保存和岗位匹配授权
CREATE TABLE biz_user_consent (
  user_consent_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  consent_code VARCHAR(64) NOT NULL UNIQUE,
  user_id BIGINT UNSIGNED NOT NULL,
  consent_type_code VARCHAR(32) NOT NULL
    COMMENT 'resume_process/profile_storage/job_match/model_processing/share',
  target_type_code VARCHAR(32) NOT NULL COMMENT 'resume/profile/all_personal_data',
  target_id BIGINT UNSIGNED NULL,
  consent_version VARCHAR(64) NOT NULL,
  consent_purpose VARCHAR(500) NOT NULL,
  consent_status_code VARCHAR(32) NOT NULL,
  granted_at DATETIME NOT NULL,
  withdrawn_at DATETIME NULL,
  expires_at DATETIME NULL,
  proof_json JSON NULL,
  FOREIGN KEY (user_id) REFERENCES app_user(user_id),
  CHECK (consent_status_code IN ('granted','withdrawn','expired')),
  KEY idx_consent_effective (user_id, consent_type_code, consent_status_code, expires_at)
) ENGINE=InnoDB COMMENT='[C] 简历、画像、匹配和模型处理授权';

CREATE TABLE biz_personal_data_deletion_request (
  deletion_request_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  request_code VARCHAR(64) NOT NULL UNIQUE,
  requested_by_user_id BIGINT UNSIGNED NOT NULL,
  request_scope_code VARCHAR(32) NOT NULL COMMENT 'resume/profile/all_personal_data',
  target_id BIGINT UNSIGNED NULL,
  request_status_code VARCHAR(32) NOT NULL DEFAULT 'pending',
  requested_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  completed_at DATETIME NULL,
  processing_note TEXT NULL,
  deletion_receipt_json JSON NULL,
  FOREIGN KEY (requested_by_user_id) REFERENCES app_user(user_id),
  CHECK (request_status_code IN ('pending','processing','completed','rejected')),
  KEY idx_deletion_request_user (requested_by_user_id, request_status_code, requested_at)
) ENGINE=InnoDB COMMENT='[C] 个人简历、画像和派生结果的删除或匿名化请求';

-- ============================================================================
-- 结构说明
-- 1. A类表是旧SQLite数据覆盖审查的重点；B类可由A类数据重算；C类由新系统产生。
-- 2. 真实JD只进入biz_job_posting；生成标准JD只进入biz_generated_job_description*。
-- 3. L1-L4和T1-T7是两条独立分类轴。
-- 4. 岗位聚类是算法版本对象，biz_job_role是稳定业务岗位，两者不能混为一个ID。
-- 5. 新岗位成熟阶段和审核工作流状态分开保存。
-- 6. 匹配必须绑定candidate_profile_version_id，历史结果不随当前画像更新而漂移。
-- ============================================================================
