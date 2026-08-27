"""Create ingestion ledger and technology taxonomy foundation.

Revision ID: 20260811_0001
Revises: None
Create Date: 2026-08-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260811_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

bigint_pk = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "raw_file_asset",
        sa.Column("file_asset_id", bigint_pk, primary_key=True, autoincrement=True),
        sa.Column("asset_code", sa.String(64), nullable=False),
        sa.Column("asset_type_code", sa.String(32), nullable=False),
        sa.Column("storage_object_key", sa.String(1500), nullable=False),
        sa.Column("original_file_name", sa.String(500)),
        sa.Column("mime_type", sa.String(200)),
        sa.Column("file_size_bytes", sa.BigInteger()),
        sa.Column("sha256_hash", sa.String(64), nullable=False),
        sa.Column("virus_scan_status_code", sa.String(32)),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("asset_code", name="uq_raw_file_asset_asset_code"),
        sa.UniqueConstraint("sha256_hash", "asset_type_code", name="uk_file_asset_hash_type"),
    )
    op.create_table(
        "biz_file_import_run",
        sa.Column("file_import_run_id", bigint_pk, primary_key=True, autoincrement=True),
        sa.Column("import_run_code", sa.String(64), nullable=False),
        sa.Column(
            "file_asset_id",
            bigint_pk,
            sa.ForeignKey("raw_file_asset.file_asset_id"),
            nullable=False,
        ),
        sa.Column("importer_code", sa.String(64), nullable=False),
        sa.Column("mapping_code", sa.String(64), nullable=False),
        sa.Column("mapping_version", sa.String(32), nullable=False),
        sa.Column("source_schema_hash", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(64), nullable=False),
        sa.Column("import_status_code", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("total_row_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("success_row_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped_row_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_row_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime()),
        sa.Column("completed_at", sa.DateTime()),
        sa.Column("error_summary_json", sa.JSON()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("import_run_code", name="uq_biz_file_import_run_import_run_code"),
        sa.UniqueConstraint("idempotency_key", name="uq_biz_file_import_run_idempotency_key"),
    )
    op.create_index(
        "idx_file_import_status", "biz_file_import_run", ["import_status_code", "created_at"]
    )
    op.create_index("idx_file_import_asset", "biz_file_import_run", ["file_asset_id", "created_at"])
    op.create_table(
        "raw_spreadsheet_row",
        sa.Column("spreadsheet_row_id", bigint_pk, primary_key=True, autoincrement=True),
        sa.Column(
            "file_asset_id",
            bigint_pk,
            sa.ForeignKey("raw_file_asset.file_asset_id"),
            nullable=False,
        ),
        sa.Column("sheet_name", sa.String(255), nullable=False),
        sa.Column("source_row_number", sa.Integer(), nullable=False),
        sa.Column("external_record_key", sa.String(500)),
        sa.Column("header_schema_hash", sa.String(64), nullable=False),
        sa.Column("row_content_hash", sa.String(64), nullable=False),
        sa.Column("row_payload_json", sa.JSON(), nullable=False),
        sa.Column(
            "access_classification_code",
            sa.String(32),
            nullable=False,
            server_default="project_internal",
        ),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint(
            "file_asset_id",
            "sheet_name",
            "source_row_number",
            name="uk_spreadsheet_source_row",
        ),
    )
    op.create_index("idx_spreadsheet_row_hash", "raw_spreadsheet_row", ["row_content_hash"])
    op.create_index("idx_spreadsheet_external_key", "raw_spreadsheet_row", ["external_record_key"])
    op.create_table(
        "biz_file_import_row_result",
        sa.Column("import_row_result_id", bigint_pk, primary_key=True, autoincrement=True),
        sa.Column(
            "file_import_run_id",
            bigint_pk,
            sa.ForeignKey("biz_file_import_run.file_import_run_id"),
            nullable=False,
        ),
        sa.Column(
            "spreadsheet_row_id",
            bigint_pk,
            sa.ForeignKey("raw_spreadsheet_row.spreadsheet_row_id"),
            nullable=False,
        ),
        sa.Column("row_status_code", sa.String(32), nullable=False),
        sa.Column("target_type_code", sa.String(64)),
        sa.Column("target_record_key", sa.String(128)),
        sa.Column("error_code", sa.String(64)),
        sa.Column("error_field", sa.String(255)),
        sa.Column("error_message", sa.Text()),
        sa.Column("normalized_payload_json", sa.JSON()),
        sa.Column(
            "replay_of_result_id",
            bigint_pk,
            sa.ForeignKey("biz_file_import_row_result.import_row_result_id"),
        ),
        sa.Column("processed_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint(
            "file_import_run_id",
            "spreadsheet_row_id",
            name="uk_import_run_source_row",
        ),
    )
    op.create_index(
        "idx_import_row_status",
        "biz_file_import_row_result",
        ["file_import_run_id", "row_status_code"],
    )
    op.create_index(
        "idx_import_row_target",
        "biz_file_import_row_result",
        ["target_type_code", "target_record_key"],
    )
    op.create_table(
        "md_technology_taxonomy_version",
        sa.Column("taxonomy_version_id", bigint_pk, primary_key=True, autoincrement=True),
        sa.Column("version_code", sa.String(32), nullable=False),
        sa.Column("version_name", sa.String(200), nullable=False),
        sa.Column(
            "previous_version_id",
            bigint_pk,
            sa.ForeignKey("md_technology_taxonomy_version.taxonomy_version_id"),
        ),
        sa.Column(
            "source_file_asset_id",
            bigint_pk,
            sa.ForeignKey("raw_file_asset.file_asset_id"),
            nullable=False,
        ),
        sa.Column("effective_date", sa.Date(), nullable=False),
        sa.Column("version_status_code", sa.String(32), nullable=False, server_default="draft"),
        sa.Column("change_summary", sa.Text()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("version_code", name="uq_md_technology_taxonomy_version_version_code"),
    )
    op.create_table(
        "md_technology_domain",
        sa.Column("technology_domain_id", bigint_pk, primary_key=True, autoincrement=True),
        sa.Column(
            "source_spreadsheet_row_id",
            bigint_pk,
            sa.ForeignKey("raw_spreadsheet_row.spreadsheet_row_id"),
            nullable=False,
        ),
        sa.Column("domain_version", sa.String(32), nullable=False),
        sa.Column("domain_code", sa.String(8), nullable=False),
        sa.Column("domain_name", sa.String(200), nullable=False),
        sa.Column("definition_text", sa.Text()),
        sa.Column("color_token", sa.String(32)),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("domain_version", "domain_code", name="uk_technology_domain"),
    )
    op.create_table(
        "md_technology_node",
        sa.Column("technology_node_id", bigint_pk, primary_key=True, autoincrement=True),
        sa.Column(
            "taxonomy_version_id",
            bigint_pk,
            sa.ForeignKey("md_technology_taxonomy_version.taxonomy_version_id"),
            nullable=False,
        ),
        sa.Column("technology_code", sa.String(64), nullable=False),
        sa.Column(
            "parent_technology_node_id",
            bigint_pk,
            sa.ForeignKey("md_technology_node.technology_node_id"),
        ),
        sa.Column(
            "source_spreadsheet_row_id",
            bigint_pk,
            sa.ForeignKey("raw_spreadsheet_row.spreadsheet_row_id"),
            nullable=False,
        ),
        sa.Column("level_code", sa.String(8), nullable=False),
        sa.Column("technology_name", sa.String(500), nullable=False),
        sa.Column("normalized_name", sa.String(500), nullable=False),
        sa.Column("node_type_code", sa.String(32), nullable=False, server_default="standard"),
        sa.Column("semantic_role_code", sa.String(32)),
        sa.Column("definition_text", sa.Text()),
        sa.Column("governance_status_code", sa.String(32), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint(
            "taxonomy_version_id", "technology_code", name="uk_technology_version_code"
        ),
        sa.UniqueConstraint(
            "taxonomy_version_id",
            "parent_technology_node_id",
            "normalized_name",
            name="uk_technology_parent_name",
        ),
    )
    op.create_index(
        "idx_technology_level",
        "md_technology_node",
        ["taxonomy_version_id", "level_code", "governance_status_code"],
    )
    op.create_table(
        "md_technology_alias",
        sa.Column("technology_alias_id", bigint_pk, primary_key=True, autoincrement=True),
        sa.Column(
            "technology_node_id",
            bigint_pk,
            sa.ForeignKey("md_technology_node.technology_node_id"),
            nullable=False,
        ),
        sa.Column(
            "source_spreadsheet_row_id",
            bigint_pk,
            sa.ForeignKey("raw_spreadsheet_row.spreadsheet_row_id"),
            nullable=False,
        ),
        sa.Column("alias_text", sa.String(500), nullable=False),
        sa.Column("normalized_alias", sa.String(500), nullable=False),
        sa.Column("alias_type_code", sa.String(32), nullable=False),
        sa.Column("source_type_code", sa.String(32)),
        sa.Column("source_metadata_json", sa.JSON()),
        sa.Column("is_matchable", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("technology_node_id", "normalized_alias", name="uk_technology_alias"),
    )
    op.create_index(
        "idx_technology_alias_lookup",
        "md_technology_alias",
        ["normalized_alias", "is_matchable"],
    )
    op.create_table(
        "rel_technology_node_domain",
        sa.Column(
            "technology_node_id",
            bigint_pk,
            sa.ForeignKey("md_technology_node.technology_node_id"),
            primary_key=True,
        ),
        sa.Column(
            "technology_domain_id",
            bigint_pk,
            sa.ForeignKey("md_technology_domain.technology_domain_id"),
            primary_key=True,
        ),
        sa.Column(
            "source_spreadsheet_row_id",
            bigint_pk,
            sa.ForeignKey("raw_spreadsheet_row.spreadsheet_row_id"),
            nullable=False,
        ),
        sa.Column("domain_score", sa.Numeric(7, 4), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("evidence_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("calculation_version", sa.String(64)),
        sa.Column("review_status_code", sa.String(32), nullable=False, server_default="confirmed"),
    )


def downgrade() -> None:
    op.drop_table("rel_technology_node_domain")
    op.drop_index("idx_technology_alias_lookup", table_name="md_technology_alias")
    op.drop_table("md_technology_alias")
    op.drop_index("idx_technology_level", table_name="md_technology_node")
    op.drop_table("md_technology_node")
    op.drop_table("md_technology_domain")
    op.drop_table("md_technology_taxonomy_version")
    op.drop_index("idx_import_row_target", table_name="biz_file_import_row_result")
    op.drop_index("idx_import_row_status", table_name="biz_file_import_row_result")
    op.drop_table("biz_file_import_row_result")
    op.drop_index("idx_spreadsheet_external_key", table_name="raw_spreadsheet_row")
    op.drop_index("idx_spreadsheet_row_hash", table_name="raw_spreadsheet_row")
    op.drop_table("raw_spreadsheet_row")
    op.drop_index("idx_file_import_asset", table_name="biz_file_import_run")
    op.drop_index("idx_file_import_status", table_name="biz_file_import_run")
    op.drop_table("biz_file_import_run")
    op.drop_table("raw_file_asset")
