"""add collection, milestone, and unified review pipeline

Revision ID: 20260811_0004
Revises: 20260811_0003
Create Date: 2026-08-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260811_0004"
down_revision: str | None = "20260811_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def pk_type():
    return sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def now():
    return sa.text("(CURRENT_TIMESTAMP)")


def upgrade() -> None:
    op.create_table(
        "app_user",
        sa.Column("user_id", pk_type(), nullable=False),
        sa.Column("user_code", sa.String(64), nullable=False),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("role_code", sa.String(32), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=now(), nullable=False),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_app_user")),
        sa.UniqueConstraint("user_code", name=op.f("uq_app_user_user_code")),
    )
    op.create_table(
        "md_source_collection_policy",
        sa.Column("collection_policy_id", pk_type(), nullable=False),
        sa.Column("data_source_id", pk_type(), nullable=False),
        sa.Column("policy_version", sa.String(64), nullable=False),
        sa.Column("list_page_rule_json", sa.JSON(), nullable=True),
        sa.Column("detail_page_rule_json", sa.JSON(), nullable=True),
        sa.Column("pagination_rule_json", sa.JSON(), nullable=True),
        sa.Column("max_depth", sa.Integer(), nullable=False),
        sa.Column("schedule_cron", sa.String(100), nullable=True),
        sa.Column("timezone_name", sa.String(64), nullable=False),
        sa.Column("rate_limit_per_minute", sa.Integer(), nullable=False),
        sa.Column("domain_concurrency", sa.Integer(), nullable=False),
        sa.Column("robots_status_code", sa.String(32), nullable=False),
        sa.Column("terms_checked", sa.Boolean(), nullable=False),
        sa.Column("allowed_scope_json", sa.JSON(), nullable=True),
        sa.Column("parser_code", sa.String(64), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=now(), nullable=False),
        sa.CheckConstraint(
            "max_depth >= 0 AND max_depth <= 1",
            name=op.f("ck_md_source_collection_policy_collection_policy_depth"),
        ),
        sa.ForeignKeyConstraint(
            ["data_source_id"],
            ["md_data_source.data_source_id"],
            name=op.f("fk_md_source_collection_policy_data_source_id_md_data_source"),
        ),
        sa.PrimaryKeyConstraint(
            "collection_policy_id", name=op.f("pk_md_source_collection_policy")
        ),
        sa.UniqueConstraint("data_source_id", "policy_version", name="uk_source_policy_version"),
    )
    op.create_table(
        "biz_collection_run",
        sa.Column("collection_run_id", pk_type(), nullable=False),
        sa.Column("run_code", sa.String(64), nullable=False),
        sa.Column("data_source_id", pk_type(), nullable=False),
        sa.Column("collection_policy_id", pk_type(), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("run_status_code", sa.String(32), nullable=False),
        sa.Column("discovered_count", sa.Integer(), nullable=False),
        sa.Column("changed_count", sa.Integer(), nullable=False),
        sa.Column("unchanged_count", sa.Integer(), nullable=False),
        sa.Column("failed_count", sa.Integer(), nullable=False),
        sa.Column("cursor_json", sa.JSON(), nullable=True),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["collection_policy_id"],
            ["md_source_collection_policy.collection_policy_id"],
            name=op.f("fk_biz_collection_run_collection_policy_id_md_source_collection_policy"),
        ),
        sa.ForeignKeyConstraint(
            ["data_source_id"],
            ["md_data_source.data_source_id"],
            name=op.f("fk_biz_collection_run_data_source_id_md_data_source"),
        ),
        sa.PrimaryKeyConstraint("collection_run_id", name=op.f("pk_biz_collection_run")),
        sa.UniqueConstraint("run_code", name=op.f("uq_biz_collection_run_run_code")),
    )
    op.create_index(
        "idx_collection_run_status", "biz_collection_run", ["run_status_code", "scheduled_at"]
    )
    op.create_table(
        "biz_collection_request",
        sa.Column("collection_request_id", pk_type(), nullable=False),
        sa.Column("collection_run_id", pk_type(), nullable=False),
        sa.Column("parent_request_id", pk_type(), nullable=True),
        sa.Column("request_url", sa.String(1500), nullable=False),
        sa.Column("normalized_url_hash", sa.String(64), nullable=False),
        sa.Column("request_depth", sa.Integer(), nullable=False),
        sa.Column("request_type_code", sa.String(32), nullable=False),
        sa.Column("response_status_code", sa.Integer(), nullable=True),
        sa.Column("response_content_hash", sa.String(64), nullable=True),
        sa.Column("response_file_asset_id", pk_type(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("request_status_code", sa.String(32), nullable=False),
        sa.Column("parse_status_code", sa.String(32), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("requested_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "request_depth >= 0 AND request_depth <= 1",
            name=op.f("ck_biz_collection_request_collection_request_depth"),
        ),
        sa.ForeignKeyConstraint(
            ["collection_run_id"],
            ["biz_collection_run.collection_run_id"],
            name=op.f("fk_biz_collection_request_collection_run_id_biz_collection_run"),
        ),
        sa.ForeignKeyConstraint(
            ["parent_request_id"],
            ["biz_collection_request.collection_request_id"],
            name=op.f("fk_biz_collection_request_parent_request_id_biz_collection_request"),
        ),
        sa.ForeignKeyConstraint(
            ["response_file_asset_id"],
            ["raw_file_asset.file_asset_id"],
            name=op.f("fk_biz_collection_request_response_file_asset_id_raw_file_asset"),
        ),
        sa.PrimaryKeyConstraint("collection_request_id", name=op.f("pk_biz_collection_request")),
        sa.UniqueConstraint(
            "collection_run_id", "normalized_url_hash", name="uk_collection_request_url"
        ),
    )
    op.create_index(
        "idx_collection_request_status",
        "biz_collection_request",
        ["collection_run_id", "request_status_code"],
    )
    op.create_table(
        "biz_extraction_run",
        sa.Column("extraction_run_id", pk_type(), nullable=False),
        sa.Column("run_code", sa.String(64), nullable=False),
        sa.Column("source_document_version_id", pk_type(), nullable=False),
        sa.Column("extractor_code", sa.String(64), nullable=False),
        sa.Column("extractor_version", sa.String(64), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("run_status_code", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_document_version_id"],
            ["raw_source_document_version.source_document_version_id"],
            name=op.f(
                "fk_biz_extraction_run_source_document_version_id_raw_source_document_version"
            ),
        ),
        sa.PrimaryKeyConstraint("extraction_run_id", name=op.f("pk_biz_extraction_run")),
        sa.UniqueConstraint("run_code", name=op.f("uq_biz_extraction_run_run_code")),
    )
    op.create_table(
        "biz_extracted_fact",
        sa.Column("extracted_fact_id", pk_type(), nullable=False),
        sa.Column("extraction_run_id", pk_type(), nullable=False),
        sa.Column("fact_code", sa.String(64), nullable=False),
        sa.Column("fact_type_code", sa.String(32), nullable=False),
        sa.Column("normalized_value_json", sa.JSON(), nullable=False),
        sa.Column("extraction_confidence_score", sa.Numeric(5, 2), nullable=False),
        sa.Column("publish_score", sa.Numeric(5, 2), nullable=False),
        sa.Column("fact_status_code", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["extraction_run_id"],
            ["biz_extraction_run.extraction_run_id"],
            name=op.f("fk_biz_extracted_fact_extraction_run_id_biz_extraction_run"),
        ),
        sa.PrimaryKeyConstraint("extracted_fact_id", name=op.f("pk_biz_extracted_fact")),
        sa.UniqueConstraint("fact_code", name=op.f("uq_biz_extracted_fact_fact_code")),
    )
    op.create_index(
        "idx_extracted_fact_status", "biz_extracted_fact", ["fact_type_code", "fact_status_code"]
    )
    op.create_table(
        "biz_fact_validation",
        sa.Column("fact_validation_id", pk_type(), nullable=False),
        sa.Column("extracted_fact_id", pk_type(), nullable=False),
        sa.Column("validator_code", sa.String(64), nullable=False),
        sa.Column("validation_status_code", sa.String(32), nullable=False),
        sa.Column("hard_error_count", sa.Integer(), nullable=False),
        sa.Column("score_breakdown_json", sa.JSON(), nullable=False),
        sa.Column("reason_json", sa.JSON(), nullable=True),
        sa.Column("validated_at", sa.DateTime(), server_default=now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["extracted_fact_id"],
            ["biz_extracted_fact.extracted_fact_id"],
            name=op.f("fk_biz_fact_validation_extracted_fact_id_biz_extracted_fact"),
        ),
        sa.PrimaryKeyConstraint("fact_validation_id", name=op.f("pk_biz_fact_validation")),
    )
    op.create_table(
        "rel_fact_evidence",
        sa.Column("extracted_fact_id", pk_type(), nullable=False),
        sa.Column("evidence_span_id", pk_type(), nullable=False),
        sa.Column("support_type_code", sa.String(32), nullable=False),
        sa.Column("support_score", sa.Numeric(5, 2), nullable=False),
        sa.ForeignKeyConstraint(
            ["evidence_span_id"],
            ["biz_evidence_span.evidence_span_id"],
            name=op.f("fk_rel_fact_evidence_evidence_span_id_biz_evidence_span"),
        ),
        sa.ForeignKeyConstraint(
            ["extracted_fact_id"],
            ["biz_extracted_fact.extracted_fact_id"],
            name=op.f("fk_rel_fact_evidence_extracted_fact_id_biz_extracted_fact"),
        ),
        sa.PrimaryKeyConstraint(
            "extracted_fact_id", "evidence_span_id", name=op.f("pk_rel_fact_evidence")
        ),
    )
    op.create_table(
        "biz_milestone_event",
        sa.Column("milestone_event_id", pk_type(), nullable=False),
        sa.Column("milestone_code", sa.String(64), nullable=False),
        sa.Column("extracted_fact_id", pk_type(), nullable=False),
        sa.Column("milestone_name", sa.String(500), nullable=False),
        sa.Column("milestone_type_code", sa.String(32), nullable=False),
        sa.Column("event_date", sa.Date(), nullable=True),
        sa.Column("event_year", sa.Integer(), nullable=False),
        sa.Column("description_text", sa.Text(), nullable=False),
        sa.Column("maturity_delta_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("verification_status_code", sa.String(32), nullable=False),
        sa.Column("verified_by_user_id", pk_type(), nullable=True),
        sa.Column("verified_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=now(), nullable=False),
        sa.CheckConstraint(
            "event_year >= 1900 AND event_year <= 2200",
            name=op.f("ck_biz_milestone_event_milestone_event_year"),
        ),
        sa.ForeignKeyConstraint(
            ["extracted_fact_id"],
            ["biz_extracted_fact.extracted_fact_id"],
            name=op.f("fk_biz_milestone_event_extracted_fact_id_biz_extracted_fact"),
        ),
        sa.ForeignKeyConstraint(
            ["verified_by_user_id"],
            ["app_user.user_id"],
            name=op.f("fk_biz_milestone_event_verified_by_user_id_app_user"),
        ),
        sa.PrimaryKeyConstraint("milestone_event_id", name=op.f("pk_biz_milestone_event")),
        sa.UniqueConstraint(
            "extracted_fact_id", name=op.f("uq_biz_milestone_event_extracted_fact_id")
        ),
        sa.UniqueConstraint("milestone_code", name=op.f("uq_biz_milestone_event_milestone_code")),
    )
    op.create_index(
        "idx_milestone_status_year",
        "biz_milestone_event",
        ["verification_status_code", "event_year"],
    )
    op.create_table(
        "biz_review_task",
        sa.Column("review_task_id", pk_type(), nullable=False),
        sa.Column("task_code", sa.String(64), nullable=False),
        sa.Column("queue_code", sa.String(32), nullable=False),
        sa.Column("target_type_code", sa.String(32), nullable=False),
        sa.Column("target_id", sa.BigInteger(), nullable=False),
        sa.Column("priority_score", sa.Numeric(7, 2), nullable=False),
        sa.Column("task_status_code", sa.String(32), nullable=False),
        sa.Column("assigned_user_id", pk_type(), nullable=True),
        sa.Column("target_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("reason_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["assigned_user_id"],
            ["app_user.user_id"],
            name=op.f("fk_biz_review_task_assigned_user_id_app_user"),
        ),
        sa.PrimaryKeyConstraint("review_task_id", name=op.f("pk_biz_review_task")),
        sa.UniqueConstraint("queue_code", "target_type_code", "target_id", name="uk_review_target"),
        sa.UniqueConstraint("task_code", name=op.f("uq_biz_review_task_task_code")),
    )
    op.create_index(
        "idx_review_queue_status",
        "biz_review_task",
        ["queue_code", "task_status_code", "priority_score"],
    )
    op.create_table(
        "biz_review_action",
        sa.Column("review_action_id", pk_type(), nullable=False),
        sa.Column("review_task_id", pk_type(), nullable=False),
        sa.Column("actor_user_id", pk_type(), nullable=False),
        sa.Column("action_code", sa.String(32), nullable=False),
        sa.Column("from_status_code", sa.String(32), nullable=False),
        sa.Column("to_status_code", sa.String(32), nullable=False),
        sa.Column("comment_text", sa.Text(), nullable=True),
        sa.Column("before_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("after_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("acted_at", sa.DateTime(), server_default=now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["app_user.user_id"],
            name=op.f("fk_biz_review_action_actor_user_id_app_user"),
        ),
        sa.ForeignKeyConstraint(
            ["review_task_id"],
            ["biz_review_task.review_task_id"],
            name=op.f("fk_biz_review_action_review_task_id_biz_review_task"),
        ),
        sa.PrimaryKeyConstraint("review_action_id", name=op.f("pk_biz_review_action")),
    )
    op.create_table(
        "rel_milestone_technology",
        sa.Column("milestone_event_id", pk_type(), nullable=False),
        sa.Column("technology_node_id", pk_type(), nullable=False),
        sa.Column("relation_type_code", sa.String(32), nullable=False),
        sa.Column("relevance_score", sa.Numeric(5, 2), nullable=False),
        sa.Column("is_human_confirmed", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["milestone_event_id"],
            ["biz_milestone_event.milestone_event_id"],
            name=op.f("fk_rel_milestone_technology_milestone_event_id_biz_milestone_event"),
        ),
        sa.ForeignKeyConstraint(
            ["technology_node_id"],
            ["md_technology_node.technology_node_id"],
            name=op.f("fk_rel_milestone_technology_technology_node_id_md_technology_node"),
        ),
        sa.PrimaryKeyConstraint(
            "milestone_event_id", "technology_node_id", name=op.f("pk_rel_milestone_technology")
        ),
    )
    op.create_table(
        "rel_milestone_evidence",
        sa.Column("milestone_event_id", pk_type(), nullable=False),
        sa.Column("evidence_span_id", pk_type(), nullable=False),
        sa.Column("evidence_role_code", sa.String(32), nullable=False),
        sa.ForeignKeyConstraint(
            ["evidence_span_id"],
            ["biz_evidence_span.evidence_span_id"],
            name=op.f("fk_rel_milestone_evidence_evidence_span_id_biz_evidence_span"),
        ),
        sa.ForeignKeyConstraint(
            ["milestone_event_id"],
            ["biz_milestone_event.milestone_event_id"],
            name=op.f("fk_rel_milestone_evidence_milestone_event_id_biz_milestone_event"),
        ),
        sa.PrimaryKeyConstraint(
            "milestone_event_id", "evidence_span_id", name=op.f("pk_rel_milestone_evidence")
        ),
    )


def downgrade() -> None:
    op.drop_table("rel_milestone_evidence")
    op.drop_table("rel_milestone_technology")
    op.drop_table("biz_review_action")
    op.drop_index("idx_review_queue_status", table_name="biz_review_task")
    op.drop_table("biz_review_task")
    op.drop_index("idx_milestone_status_year", table_name="biz_milestone_event")
    op.drop_table("biz_milestone_event")
    op.drop_table("rel_fact_evidence")
    op.drop_table("biz_fact_validation")
    op.drop_index("idx_extracted_fact_status", table_name="biz_extracted_fact")
    op.drop_table("biz_extracted_fact")
    op.drop_table("biz_extraction_run")
    op.drop_index("idx_collection_request_status", table_name="biz_collection_request")
    op.drop_table("biz_collection_request")
    op.drop_index("idx_collection_run_status", table_name="biz_collection_run")
    op.drop_table("biz_collection_run")
    op.drop_table("md_source_collection_policy")
    op.drop_table("app_user")
