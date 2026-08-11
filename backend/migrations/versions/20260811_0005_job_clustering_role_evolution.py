"""add job clustering and role evolution foundation

Revision ID: 20260811_0005
Revises: 20260811_0004
Create Date: 2026-08-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260811_0005"
down_revision: str | None = "20260811_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def pk_type():
    return sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def now():
    return sa.text("(CURRENT_TIMESTAMP)")


def upgrade() -> None:
    op.create_table(
        "biz_job_clustering_run",
        sa.Column("clustering_run_id", pk_type(), nullable=False),
        sa.Column("run_code", sa.String(64), nullable=False),
        sa.Column("job_parse_run_id", pk_type(), nullable=False),
        sa.Column("run_type_code", sa.String(32), nullable=False),
        sa.Column("target_date", sa.Date(), nullable=False),
        sa.Column("window_start_date", sa.Date(), nullable=True),
        sa.Column("feature_version", sa.String(64), nullable=False),
        sa.Column("embedding_model_version", sa.String(100), nullable=True),
        sa.Column("algorithm_name", sa.String(100), nullable=False),
        sa.Column("algorithm_version", sa.String(64), nullable=False),
        sa.Column("parameter_json", sa.JSON(), nullable=False),
        sa.Column("input_snapshot_hash", sa.String(64), nullable=False),
        sa.Column("input_job_count", sa.Integer(), nullable=False),
        sa.Column("assigned_job_count", sa.Integer(), nullable=False),
        sa.Column("grey_job_count", sa.Integer(), nullable=False),
        sa.Column("output_cluster_count", sa.Integer(), nullable=False),
        sa.Column("candidate_role_count", sa.Integer(), nullable=False),
        sa.Column("quality_metric_json", sa.JSON(), nullable=True),
        sa.Column("run_status_code", sa.String(32), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["job_parse_run_id"],
            ["biz_job_parse_run.job_parse_run_id"],
            name=op.f("fk_biz_job_clustering_run_job_parse_run_id_biz_job_parse_run"),
        ),
        sa.PrimaryKeyConstraint("clustering_run_id", name=op.f("pk_biz_job_clustering_run")),
        sa.UniqueConstraint(
            "job_parse_run_id",
            "algorithm_version",
            "input_snapshot_hash",
            name="uk_clustering_run_input",
        ),
        sa.UniqueConstraint("run_code", name=op.f("uq_biz_job_clustering_run_run_code")),
    )
    op.create_index(
        "idx_clustering_run_status",
        "biz_job_clustering_run",
        ["run_status_code", "target_date"],
    )
    op.create_table(
        "biz_job_cluster_version",
        sa.Column("job_cluster_version_id", pk_type(), nullable=False),
        sa.Column("clustering_run_id", pk_type(), nullable=False),
        sa.Column("stable_cluster_code", sa.String(64), nullable=False),
        sa.Column("cluster_label", sa.String(300), nullable=False),
        sa.Column("cluster_description", sa.Text(), nullable=True),
        sa.Column("member_count", sa.Integer(), nullable=False),
        sa.Column("independent_organization_count", sa.Integer(), nullable=False),
        sa.Column("centroid_json", sa.JSON(), nullable=False),
        sa.Column("representative_job_ids_json", sa.JSON(), nullable=False),
        sa.Column("silhouette_score", sa.Numeric(8, 6), nullable=True),
        sa.Column("coherence_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("cluster_status_code", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["clustering_run_id"],
            ["biz_job_clustering_run.clustering_run_id"],
            name=op.f("fk_biz_job_cluster_version_clustering_run_id_biz_job_clustering_run"),
        ),
        sa.PrimaryKeyConstraint("job_cluster_version_id", name=op.f("pk_biz_job_cluster_version")),
        sa.UniqueConstraint(
            "clustering_run_id", "stable_cluster_code", name="uk_cluster_run_stable"
        ),
    )
    op.create_index(
        "idx_cluster_run_size",
        "biz_job_cluster_version",
        ["clustering_run_id", "member_count"],
    )
    op.create_table(
        "biz_job_role",
        sa.Column("job_role_id", pk_type(), nullable=False),
        sa.Column("role_code", sa.String(64), nullable=False),
        sa.Column("canonical_name", sa.String(300), nullable=False),
        sa.Column("normalized_name", sa.String(300), nullable=False),
        sa.Column("origin_type_code", sa.String(32), nullable=False),
        sa.Column("lifecycle_status_code", sa.String(32), nullable=False),
        sa.Column("first_detected_at", sa.DateTime(), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=now(), nullable=False),
        sa.PrimaryKeyConstraint("job_role_id", name=op.f("pk_biz_job_role")),
        sa.UniqueConstraint("canonical_name", name=op.f("uq_biz_job_role_canonical_name")),
        sa.UniqueConstraint("normalized_name", name=op.f("uq_biz_job_role_normalized_name")),
        sa.UniqueConstraint("role_code", name=op.f("uq_biz_job_role_role_code")),
    )
    op.create_table(
        "rel_job_cluster_member",
        sa.Column("job_cluster_version_id", pk_type(), nullable=False),
        sa.Column("job_posting_id", pk_type(), nullable=False),
        sa.Column("similarity_score", sa.Numeric(7, 6), nullable=False),
        sa.Column("assignment_method_code", sa.String(32), nullable=False),
        sa.Column("assignment_status_code", sa.String(32), nullable=False),
        sa.Column("assignment_confidence", sa.Numeric(5, 2), nullable=True),
        sa.Column("similarity_breakdown_json", sa.JSON(), nullable=False),
        sa.Column("top_candidates_json", sa.JSON(), nullable=False),
        sa.Column("is_representative", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["job_cluster_version_id"],
            ["biz_job_cluster_version.job_cluster_version_id"],
            name=op.f("fk_rel_job_cluster_member_job_cluster_version_id_biz_job_cluster_version"),
        ),
        sa.ForeignKeyConstraint(
            ["job_posting_id"],
            ["biz_job_posting.job_posting_id"],
            name=op.f("fk_rel_job_cluster_member_job_posting_id_biz_job_posting"),
        ),
        sa.PrimaryKeyConstraint(
            "job_cluster_version_id", "job_posting_id", name=op.f("pk_rel_job_cluster_member")
        ),
    )
    op.create_index("idx_cluster_member_job", "rel_job_cluster_member", ["job_posting_id"])
    op.create_table(
        "rel_job_cluster_lineage",
        sa.Column("job_cluster_lineage_id", pk_type(), nullable=False),
        sa.Column("from_cluster_version_id", pk_type(), nullable=True),
        sa.Column("to_cluster_version_id", pk_type(), nullable=True),
        sa.Column("lineage_type_code", sa.String(32), nullable=False),
        sa.Column("member_overlap_score", sa.Numeric(7, 6), nullable=True),
        sa.Column("explanation_text", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["from_cluster_version_id"],
            ["biz_job_cluster_version.job_cluster_version_id"],
            name=op.f("fk_rel_job_cluster_lineage_from_cluster_version_id_biz_job_cluster_version"),
        ),
        sa.ForeignKeyConstraint(
            ["to_cluster_version_id"],
            ["biz_job_cluster_version.job_cluster_version_id"],
            name=op.f("fk_rel_job_cluster_lineage_to_cluster_version_id_biz_job_cluster_version"),
        ),
        sa.PrimaryKeyConstraint("job_cluster_lineage_id", name=op.f("pk_rel_job_cluster_lineage")),
        sa.UniqueConstraint(
            "from_cluster_version_id",
            "to_cluster_version_id",
            "lineage_type_code",
            name="uk_cluster_lineage",
        ),
    )
    op.create_table(
        "rel_job_cluster_domain",
        sa.Column("job_cluster_version_id", pk_type(), nullable=False),
        sa.Column("technology_domain_id", pk_type(), nullable=False),
        sa.Column("domain_score", sa.Numeric(5, 2), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False),
        sa.Column("evidence_count", sa.Integer(), nullable=False),
        sa.Column("calculation_version", sa.String(64), nullable=False),
        sa.Column("review_status_code", sa.String(32), nullable=False),
        sa.ForeignKeyConstraint(
            ["job_cluster_version_id"],
            ["biz_job_cluster_version.job_cluster_version_id"],
            name=op.f("fk_rel_job_cluster_domain_job_cluster_version_id_biz_job_cluster_version"),
        ),
        sa.ForeignKeyConstraint(
            ["technology_domain_id"],
            ["md_technology_domain.technology_domain_id"],
            name=op.f("fk_rel_job_cluster_domain_technology_domain_id_md_technology_domain"),
        ),
        sa.PrimaryKeyConstraint(
            "job_cluster_version_id",
            "technology_domain_id",
            name=op.f("pk_rel_job_cluster_domain"),
        ),
    )
    op.create_table(
        "md_job_role_alias",
        sa.Column("job_role_alias_id", pk_type(), nullable=False),
        sa.Column("job_role_id", pk_type(), nullable=False),
        sa.Column("alias_text", sa.String(500), nullable=False),
        sa.Column("normalized_alias", sa.String(500), nullable=False),
        sa.Column("alias_type_code", sa.String(32), nullable=False),
        sa.Column("is_searchable", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["job_role_id"],
            ["biz_job_role.job_role_id"],
            name=op.f("fk_md_job_role_alias_job_role_id_biz_job_role"),
        ),
        sa.PrimaryKeyConstraint("job_role_alias_id", name=op.f("pk_md_job_role_alias")),
        sa.UniqueConstraint("job_role_id", "normalized_alias", name="uk_role_alias"),
    )
    op.create_index(
        "idx_role_alias_lookup", "md_job_role_alias", ["normalized_alias", "is_searchable"]
    )
    op.create_table(
        "biz_job_role_version",
        sa.Column("job_role_version_id", pk_type(), nullable=False),
        sa.Column("job_role_id", pk_type(), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("previous_version_id", pk_type(), nullable=True),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("role_name", sa.String(300), nullable=False),
        sa.Column("one_line_definition", sa.Text(), nullable=False),
        sa.Column("core_responsibility_text", sa.Text(), nullable=False),
        sa.Column("job_level_distribution_json", sa.JSON(), nullable=True),
        sa.Column("update_summary", sa.Text(), nullable=True),
        sa.Column("generation_method_code", sa.String(32), nullable=False),
        sa.Column("evidence_strength_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("approval_status_code", sa.String(32), nullable=False),
        sa.Column("approved_by_user_id", pk_type(), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["approved_by_user_id"],
            ["app_user.user_id"],
            name=op.f("fk_biz_job_role_version_approved_by_user_id_app_user"),
        ),
        sa.ForeignKeyConstraint(
            ["job_role_id"],
            ["biz_job_role.job_role_id"],
            name=op.f("fk_biz_job_role_version_job_role_id_biz_job_role"),
        ),
        sa.ForeignKeyConstraint(
            ["previous_version_id"],
            ["biz_job_role_version.job_role_version_id"],
            name=op.f("fk_biz_job_role_version_previous_version_id_biz_job_role_version"),
        ),
        sa.PrimaryKeyConstraint("job_role_version_id", name=op.f("pk_biz_job_role_version")),
        sa.UniqueConstraint("job_role_id", "version_no", name="uk_role_version_no"),
    )
    op.create_index(
        "idx_role_version_current",
        "biz_job_role_version",
        ["job_role_id", "approval_status_code", "valid_to"],
    )
    op.create_table(
        "rel_job_cluster_role",
        sa.Column("job_cluster_version_id", pk_type(), nullable=False),
        sa.Column("job_role_id", pk_type(), nullable=False),
        sa.Column("relation_type_code", sa.String(32), nullable=False),
        sa.Column("confidence_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["job_cluster_version_id"],
            ["biz_job_cluster_version.job_cluster_version_id"],
            name=op.f("fk_rel_job_cluster_role_job_cluster_version_id_biz_job_cluster_version"),
        ),
        sa.ForeignKeyConstraint(
            ["job_role_id"],
            ["biz_job_role.job_role_id"],
            name=op.f("fk_rel_job_cluster_role_job_role_id_biz_job_role"),
        ),
        sa.PrimaryKeyConstraint(
            "job_cluster_version_id",
            "job_role_id",
            "relation_type_code",
            name=op.f("pk_rel_job_cluster_role"),
        ),
    )
    op.create_table(
        "rel_job_role_version_requirement",
        sa.Column("role_version_requirement_id", pk_type(), nullable=False),
        sa.Column("job_role_version_id", pk_type(), nullable=False),
        sa.Column("technology_node_id", pk_type(), nullable=False),
        sa.Column("requirement_type_code", sa.String(32), nullable=False),
        sa.Column("required_level_code", sa.String(32), nullable=True),
        sa.Column("long_term_importance_score", sa.Numeric(5, 2), nullable=False),
        sa.Column("recent_activity_score", sa.Numeric(5, 2), nullable=False),
        sa.Column("coverage_rate", sa.Numeric(9, 6), nullable=True),
        sa.Column("required_ratio", sa.Numeric(9, 6), nullable=True),
        sa.Column("trend_score", sa.Numeric(7, 4), nullable=True),
        sa.Column("trend_status_code", sa.String(32), nullable=False),
        sa.Column("supporting_job_count", sa.Integer(), nullable=False),
        sa.Column("independent_organization_count", sa.Integer(), nullable=False),
        sa.Column("independent_source_count", sa.Integer(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=True),
        sa.Column("confidence_score", sa.Numeric(5, 2), nullable=False),
        sa.Column("is_human_edited", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["job_role_version_id"],
            ["biz_job_role_version.job_role_version_id"],
            name=op.f(
                "fk_rel_job_role_version_requirement_job_role_version_id_biz_job_role_version"
            ),
        ),
        sa.ForeignKeyConstraint(
            ["technology_node_id"],
            ["md_technology_node.technology_node_id"],
            name=op.f("fk_rel_job_role_version_requirement_technology_node_id_md_technology_node"),
        ),
        sa.PrimaryKeyConstraint(
            "role_version_requirement_id",
            name=op.f("pk_rel_job_role_version_requirement"),
        ),
        sa.UniqueConstraint(
            "job_role_version_id",
            "technology_node_id",
            "requirement_type_code",
            name="uk_role_version_technology",
        ),
    )
    op.create_index(
        "idx_role_requirement_graph",
        "rel_job_role_version_requirement",
        ["job_role_version_id", "requirement_type_code", "long_term_importance_score"],
    )
    op.create_table(
        "rel_job_role_evidence",
        sa.Column("job_role_evidence_id", pk_type(), nullable=False),
        sa.Column("job_role_version_id", pk_type(), nullable=False),
        sa.Column("role_version_requirement_id", pk_type(), nullable=True),
        sa.Column("evidence_span_id", pk_type(), nullable=False),
        sa.Column("evidence_role_code", sa.String(32), nullable=False),
        sa.Column("support_type_code", sa.String(32), nullable=False),
        sa.Column("support_score", sa.Numeric(5, 2), nullable=False),
        sa.Column("source_organization_id", pk_type(), nullable=True),
        sa.ForeignKeyConstraint(
            ["evidence_span_id"],
            ["biz_evidence_span.evidence_span_id"],
            name=op.f("fk_rel_job_role_evidence_evidence_span_id_biz_evidence_span"),
        ),
        sa.ForeignKeyConstraint(
            ["job_role_version_id"],
            ["biz_job_role_version.job_role_version_id"],
            name=op.f("fk_rel_job_role_evidence_job_role_version_id_biz_job_role_version"),
        ),
        sa.ForeignKeyConstraint(
            ["role_version_requirement_id"],
            ["rel_job_role_version_requirement.role_version_requirement_id"],
            name=op.f(
                "fk_rel_job_role_evidence_role_version_requirement_id_rel_job_role_version_requirement"
            ),
        ),
        sa.ForeignKeyConstraint(
            ["source_organization_id"],
            ["md_organization.organization_id"],
            name=op.f("fk_rel_job_role_evidence_source_organization_id_md_organization"),
        ),
        sa.PrimaryKeyConstraint("job_role_evidence_id", name=op.f("pk_rel_job_role_evidence")),
        sa.UniqueConstraint(
            "job_role_version_id",
            "role_version_requirement_id",
            "evidence_span_id",
            "evidence_role_code",
            name="uk_role_evidence",
        ),
    )
    op.create_table(
        "biz_job_evolution_event",
        sa.Column("job_evolution_event_id", pk_type(), nullable=False),
        sa.Column("event_code", sa.String(64), nullable=False),
        sa.Column("job_role_id", pk_type(), nullable=False),
        sa.Column("from_role_version_id", pk_type(), nullable=True),
        sa.Column("to_role_version_id", pk_type(), nullable=False),
        sa.Column("event_type_code", sa.String(32), nullable=False),
        sa.Column("change_summary", sa.Text(), nullable=False),
        sa.Column("confidence_score", sa.Numeric(5, 2), nullable=False),
        sa.Column("approval_status_code", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["from_role_version_id"],
            ["biz_job_role_version.job_role_version_id"],
            name=op.f("fk_biz_job_evolution_event_from_role_version_id_biz_job_role_version"),
        ),
        sa.ForeignKeyConstraint(
            ["job_role_id"],
            ["biz_job_role.job_role_id"],
            name=op.f("fk_biz_job_evolution_event_job_role_id_biz_job_role"),
        ),
        sa.ForeignKeyConstraint(
            ["to_role_version_id"],
            ["biz_job_role_version.job_role_version_id"],
            name=op.f("fk_biz_job_evolution_event_to_role_version_id_biz_job_role_version"),
        ),
        sa.PrimaryKeyConstraint("job_evolution_event_id", name=op.f("pk_biz_job_evolution_event")),
        sa.UniqueConstraint("event_code", name=op.f("uq_biz_job_evolution_event_event_code")),
    )
    op.create_table(
        "biz_job_evolution_change",
        sa.Column("job_evolution_change_id", pk_type(), nullable=False),
        sa.Column("job_evolution_event_id", pk_type(), nullable=False),
        sa.Column("technology_node_id", pk_type(), nullable=True),
        sa.Column("capability_id", sa.BigInteger(), nullable=True),
        sa.Column("change_type_code", sa.String(32), nullable=False),
        sa.Column("change_subtype_code", sa.String(32), nullable=True),
        sa.Column("old_value_json", sa.JSON(), nullable=True),
        sa.Column("new_value_json", sa.JSON(), nullable=True),
        sa.Column("change_magnitude", sa.Numeric(7, 4), nullable=True),
        sa.Column("change_reason", sa.Text(), nullable=True),
        sa.Column("evidence_count", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["job_evolution_event_id"],
            ["biz_job_evolution_event.job_evolution_event_id"],
            name=op.f("fk_biz_job_evolution_change_job_evolution_event_id_biz_job_evolution_event"),
        ),
        sa.ForeignKeyConstraint(
            ["technology_node_id"],
            ["md_technology_node.technology_node_id"],
            name=op.f("fk_biz_job_evolution_change_technology_node_id_md_technology_node"),
        ),
        sa.PrimaryKeyConstraint(
            "job_evolution_change_id", name=op.f("pk_biz_job_evolution_change")
        ),
    )
    op.create_index(
        "idx_evolution_change_event",
        "biz_job_evolution_change",
        ["job_evolution_event_id", "change_type_code"],
    )


def downgrade() -> None:
    op.drop_index("idx_evolution_change_event", table_name="biz_job_evolution_change")
    op.drop_table("biz_job_evolution_change")
    op.drop_table("biz_job_evolution_event")
    op.drop_table("rel_job_role_evidence")
    op.drop_index("idx_role_requirement_graph", table_name="rel_job_role_version_requirement")
    op.drop_table("rel_job_role_version_requirement")
    op.drop_table("rel_job_cluster_role")
    op.drop_index("idx_role_version_current", table_name="biz_job_role_version")
    op.drop_table("biz_job_role_version")
    op.drop_index("idx_role_alias_lookup", table_name="md_job_role_alias")
    op.drop_table("md_job_role_alias")
    op.drop_table("rel_job_cluster_domain")
    op.drop_table("rel_job_cluster_lineage")
    op.drop_index("idx_cluster_member_job", table_name="rel_job_cluster_member")
    op.drop_table("rel_job_cluster_member")
    op.drop_table("biz_job_role")
    op.drop_index("idx_cluster_run_size", table_name="biz_job_cluster_version")
    op.drop_table("biz_job_cluster_version")
    op.drop_index("idx_clustering_run_status", table_name="biz_job_clustering_run")
    op.drop_table("biz_job_clustering_run")
