from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.modules.ingestion.models import primary_key_type

# 机构类别（统一机构库 / 高校库 / 企业岗位库 / 科技人才库 四类来源归一）
ORG_CATEGORY_ENTERPRISE = "enterprise"  # 企业
ORG_CATEGORY_UNIVERSITY = "university"  # 高校
ORG_CATEGORY_RESEARCH = "research_institute"  # 科研院所 / 机构
ORG_CATEGORY_OTHER = "other"  # 其他

# 组织-人才关系类型
REL_EMPLOY = "employ"  # 任职 / 雇佣
REL_UNIVERSITY_AFFILIATE = "university_affiliate"  # 高校隶属（高校人才明细索引）
REL_PATENT_LINK = "patent_link"  # 专利 / 成果关联（人才机构成果关系）

# 交叉验证状态（RC-03 数据可信要求，缺失即 partial，不编造）
CV_STATUS_VERIFIED = "verified"  # 多源一致 + 有外部本体佐证
CV_STATUS_PARTIAL = "partial"  # 部分维度缺失或仅内部一致
CV_STATUS_UNVERIFIED = "unverified"  # 无外部佐证 / 数据不足


class OrganizationEntity(Base):
    """统一组织实体：企业 / 高校 / 科研机构。

    注意：本表名为 md_org_entity，刻意避开 RC-03 既有 md_organization
    （来自 migrations/versions/20260811_0002_job_data_foundation），避免表名冲突。
    raw_fields_json 保存该实体在所有来源表中的**全部原始字段**，用于图谱侧栏
    "已有字段全展示"；其余 typed 字段为图谱布局 / 筛选 / 交叉验证抽取的结构化列。
    """

    __tablename__ = "md_org_entity"

    org_id: Mapped[int] = mapped_column(primary_key_type, primary_key=True)
    org_code: Mapped[str] = mapped_column(String(32), unique=True)  # ORG-/UNI-/ENT-
    org_name: Mapped[str] = mapped_column(String(500))
    org_category: Mapped[str] = mapped_column(String(32), default=ORG_CATEGORY_OTHER)
    # 归一键（如"华为"）/ 代表名称，用于跨表与招聘数据的去重匹配
    normalized_key: Mapped[str | None] = mapped_column(String(255), index=True)

    # ---- Layer A 交叉验证：Splink 概率链接产出的归并簇 ----
    splink_cluster_id: Mapped[str | None] = mapped_column(String(64), index=True)
    splink_match_score: Mapped[float] = mapped_column(Float, default=0.0)
    dedup_source_keys: Mapped[list] = mapped_column(JSON, default=list)  # 跨表出现的原始键

    homepage_url: Mapped[str | None] = mapped_column(String(1000))
    recruit_url: Mapped[str | None] = mapped_column(String(1000))
    liepin_url: Mapped[str | None] = mapped_column(String(1000))

    hq_city: Mapped[str | None] = mapped_column(String(120))
    hq_province: Mapped[str | None] = mapped_column(String(120))
    hq_country: Mapped[str | None] = mapped_column(String(120))
    hq_district: Mapped[str | None] = mapped_column(String(120))

    industry_chain: Mapped[str | None] = mapped_column(String(64))  # 产业链(12类标准)
    tier_level: Mapped[str | None] = mapped_column(String(32))  # 层级（上游/中游/下游）
    segment: Mapped[str | None] = mapped_column(String(255))  # 细分领域
    products: Mapped[str | None] = mapped_column(Text)  # 代表产品
    product_type: Mapped[str | None] = mapped_column(String(64))  # 产品类型
    key_params: Mapped[str | None] = mapped_column(Text)  # 关键特性/参数
    mass_production: Mapped[str | None] = mapped_column(String(64))  # 量产进展
    operation_path: Mapped[str | None] = mapped_column(String(255))  # 运营路径
    financing_stage: Mapped[str | None] = mapped_column(String(64))  # 融资阶段
    financing_round: Mapped[str | None] = mapped_column(String(64))  # 融资轮次分类

    patent_family_count: Mapped[int] = mapped_column(Integer, default=0)
    standard_count: Mapped[int] = mapped_column(Integer, default=0)
    related_talent_count: Mapped[int] = mapped_column(Integer, default=0)
    university_talent_count: Mapped[int] = mapped_column(Integer, default=0)
    job_posting_count: Mapped[int] = mapped_column(Integer, default=0)  # 在聘岗位数量

    # ---- Layer B 外部真值校验 ----
    external_alignment_rate: Mapped[float] = mapped_column(Float, default=0.0)  # 技术边外部佐证比例
    cross_validation_status: Mapped[str] = mapped_column(String(32), default=CV_STATUS_UNVERIFIED)

    data_source: Mapped[str | None] = mapped_column(String(255))
    completeness: Mapped[str | None] = mapped_column(String(32))
    raw_fields_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("idx_org_entity_category", "org_category"),
        Index("idx_org_entity_chain", "industry_chain"),
    )


class OrganizationTechnology(Base):
    """组织 ↔ 标准技术（L2/L3）关系，来自各表的"标准技术标注"列。"""

    __tablename__ = "rel_org_technology"

    org_id: Mapped[int] = mapped_column(ForeignKey("md_org_entity.org_id"), primary_key=True)
    technology_code: Mapped[str] = mapped_column(String(16), primary_key=True)  # T1.05 / T1.05.02
    technology_name: Mapped[str] = mapped_column(String(255))
    level_code: Mapped[str] = mapped_column(String(8), default="L2")  # L2 / L3
    mention_count: Mapped[int] = mapped_column(Integer, default=0)  # 标注留痕中的计数
    annotation_source: Mapped[str | None] = mapped_column(String(64))  # 来源表

    # Layer B 外部真值佐证
    external_skill_label: Mapped[str | None] = mapped_column(String(255))  # 匹配的 O*NET/ESCO skill
    external_aligned: Mapped[bool] = mapped_column(Boolean, default=False)

    __table_args__ = (Index("idx_org_tech_code", "technology_code"),)


class Talent(Base):
    """科技人才实体（来自科技人才库）。"""

    __tablename__ = "md_talent"

    talent_id: Mapped[int] = mapped_column(primary_key_type, primary_key=True)
    talent_code: Mapped[str] = mapped_column(String(32), unique=True)  # PER-
    display_name: Mapped[str] = mapped_column(String(255))
    name_group: Mapped[str | None] = mapped_column(String(255))  # 姓名归并组
    talent_type: Mapped[str | None] = mapped_column(String(64))  # 人才类型
    primary_org_key: Mapped[str | None] = mapped_column(String(255))  # 主机构键
    primary_org_name: Mapped[str | None] = mapped_column(String(255))  # 主机构
    patent_family_count: Mapped[int] = mapped_column(Integer, default=0)
    standard_count: Mapped[int] = mapped_column(Integer, default=0)
    university_post_count: Mapped[int] = mapped_column(Integer, default=0)
    confidence: Mapped[str | None] = mapped_column(String(32))  # 置信度
    title: Mapped[str | None] = mapped_column(String(255))  # 职务/职称
    research_direction: Mapped[str | None] = mapped_column(Text)  # 研究方向
    technology_l2: Mapped[str | None] = mapped_column(String(500))  # 标准技术标注L2
    technology_l3: Mapped[str | None] = mapped_column(String(500))  # 标准技术标注L3
    raw_fields_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (Index("idx_talent_org", "primary_org_name"),)


class OrganizationTalent(Base):
    """组织 ↔ 人才关系（雇佣 / 高校隶属 / 专利关联）。"""

    __tablename__ = "rel_org_talent"

    org_id: Mapped[int] = mapped_column(ForeignKey("md_org_entity.org_id"), primary_key=True)
    talent_id: Mapped[int] = mapped_column(ForeignKey("md_talent.talent_id"), primary_key=True)
    relation_type: Mapped[str] = mapped_column(String(32), primary_key=True)
    source: Mapped[str | None] = mapped_column(String(64))

    __table_args__ = (Index("idx_org_talent_talent", "talent_id"),)


class TalentTechnology(Base):
    """人才 ↔ 标准技术（L2/L3）关系。"""

    __tablename__ = "rel_talent_technology"

    talent_id: Mapped[int] = mapped_column(ForeignKey("md_talent.talent_id"), primary_key=True)
    technology_code: Mapped[str] = mapped_column(String(16), primary_key=True)
    technology_name: Mapped[str] = mapped_column(String(255))
    level_code: Mapped[str] = mapped_column(String(8), default="L2")
    mention_count: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (Index("idx_talent_tech_code", "technology_code"),)


class OrganizationCrossValidation(Base):
    """组织多源交叉验证结果（RC-03 数据可信要求）。

    对比"企业业务标签（产业链/细分领域）"与"专利布局技术域"与"JD 产业链"的
    一致性，给出 0-100 一致性评分与缺失维度标记。缺失数据即标 partial，不编造。
    """

    __tablename__ = "biz_org_cross_validation"

    org_cross_validation_id: Mapped[int] = mapped_column(primary_key_type, primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("md_org_entity.org_id"), unique=True)
    consistency_score: Mapped[int] = mapped_column(Integer, default=0)
    business_chain: Mapped[str | None] = mapped_column(String(64))
    patent_domain_codes: Mapped[str | None] = mapped_column(String(255))
    jd_chain: Mapped[str | None] = mapped_column(String(64))
    matched_dimensions: Mapped[int] = mapped_column(Integer, default=0)
    missing_dimensions_json: Mapped[list] = mapped_column(JSON, default=list)
    note: Mapped[str | None] = mapped_column(Text)
    calculated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (Index("idx_org_cv_score", "consistency_score"),)
