from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.modules.ingestion.models import primary_key_type


class TechnologyTaxonomyVersion(Base):
    __tablename__ = "md_technology_taxonomy_version"

    taxonomy_version_id: Mapped[int] = mapped_column(primary_key_type, primary_key=True)
    version_code: Mapped[str] = mapped_column(String(32), unique=True)
    version_name: Mapped[str] = mapped_column(String(200))
    previous_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("md_technology_taxonomy_version.taxonomy_version_id")
    )
    source_file_asset_id: Mapped[int] = mapped_column(ForeignKey("raw_file_asset.file_asset_id"))
    effective_date: Mapped[date] = mapped_column(Date)
    version_status_code: Mapped[str] = mapped_column(String(32), default="draft")
    change_summary: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class TechnologyNode(Base):
    __tablename__ = "md_technology_node"

    technology_node_id: Mapped[int] = mapped_column(primary_key_type, primary_key=True)
    taxonomy_version_id: Mapped[int] = mapped_column(
        ForeignKey("md_technology_taxonomy_version.taxonomy_version_id")
    )
    technology_code: Mapped[str] = mapped_column(String(64))
    parent_technology_node_id: Mapped[int | None] = mapped_column(
        ForeignKey("md_technology_node.technology_node_id")
    )
    source_spreadsheet_row_id: Mapped[int] = mapped_column(
        ForeignKey("raw_spreadsheet_row.spreadsheet_row_id")
    )
    level_code: Mapped[str] = mapped_column(String(8))
    technology_name: Mapped[str] = mapped_column(String(500))
    normalized_name: Mapped[str] = mapped_column(String(500))
    node_type_code: Mapped[str] = mapped_column(String(32), default="standard")
    semantic_role_code: Mapped[str | None] = mapped_column(String(32))
    definition_text: Mapped[str | None] = mapped_column(Text)
    governance_status_code: Mapped[str] = mapped_column(String(32), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "taxonomy_version_id", "technology_code", name="uk_technology_version_code"
        ),
        UniqueConstraint(
            "taxonomy_version_id",
            "parent_technology_node_id",
            "normalized_name",
            name="uk_technology_parent_name",
        ),
        Index(
            "idx_technology_level",
            "taxonomy_version_id",
            "level_code",
            "governance_status_code",
        ),
    )


class TechnologyAlias(Base):
    __tablename__ = "md_technology_alias"

    technology_alias_id: Mapped[int] = mapped_column(primary_key_type, primary_key=True)
    technology_node_id: Mapped[int] = mapped_column(
        ForeignKey("md_technology_node.technology_node_id")
    )
    source_spreadsheet_row_id: Mapped[int] = mapped_column(
        ForeignKey("raw_spreadsheet_row.spreadsheet_row_id")
    )
    alias_text: Mapped[str] = mapped_column(String(500))
    normalized_alias: Mapped[str] = mapped_column(String(500))
    alias_type_code: Mapped[str] = mapped_column(String(32))
    source_type_code: Mapped[str | None] = mapped_column(String(32))
    source_metadata_json: Mapped[dict | None] = mapped_column(JSON)
    is_matchable: Mapped[bool] = mapped_column(Boolean, default=True)

    __table_args__ = (
        UniqueConstraint("technology_node_id", "normalized_alias", name="uk_technology_alias"),
        Index("idx_technology_alias_lookup", "normalized_alias", "is_matchable"),
    )


class TechnologyDomain(Base):
    __tablename__ = "md_technology_domain"

    technology_domain_id: Mapped[int] = mapped_column(primary_key_type, primary_key=True)
    source_spreadsheet_row_id: Mapped[int] = mapped_column(
        ForeignKey("raw_spreadsheet_row.spreadsheet_row_id")
    )
    domain_version: Mapped[str] = mapped_column(String(32))
    domain_code: Mapped[str] = mapped_column(String(8))
    domain_name: Mapped[str] = mapped_column(String(200))
    definition_text: Mapped[str | None] = mapped_column(Text)
    color_token: Mapped[str | None] = mapped_column(String(32))
    sort_order: Mapped[int] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    __table_args__ = (
        UniqueConstraint("domain_version", "domain_code", name="uk_technology_domain"),
    )


class TechnologyNodeDomain(Base):
    __tablename__ = "rel_technology_node_domain"

    technology_node_id: Mapped[int] = mapped_column(
        ForeignKey("md_technology_node.technology_node_id"), primary_key=True
    )
    technology_domain_id: Mapped[int] = mapped_column(
        ForeignKey("md_technology_domain.technology_domain_id"), primary_key=True
    )
    source_spreadsheet_row_id: Mapped[int] = mapped_column(
        ForeignKey("raw_spreadsheet_row.spreadsheet_row_id")
    )
    domain_score: Mapped[Decimal] = mapped_column(Numeric(7, 4))
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    evidence_count: Mapped[int] = mapped_column(Integer, default=0)
    calculation_version: Mapped[str | None] = mapped_column(String(64))
    review_status_code: Mapped[str] = mapped_column(String(32), default="confirmed")
