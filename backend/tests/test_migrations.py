from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


def test_initial_migration_upgrades_and_downgrades(tmp_path: Path) -> None:
    database_path = tmp_path / "migration.db"
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{database_path.as_posix()}")

    command.upgrade(config, "head")
    inspector = inspect(create_engine(f"sqlite+pysqlite:///{database_path.as_posix()}"))
    assert {
        "raw_file_asset",
        "biz_file_import_run",
        "raw_spreadsheet_row",
        "biz_file_import_row_result",
        "md_technology_taxonomy_version",
        "md_technology_domain",
        "md_technology_node",
        "md_technology_alias",
        "rel_technology_node_domain",
        "md_organization",
        "md_organization_alias",
        "md_data_source",
        "raw_source_document",
        "raw_source_document_version",
        "biz_document_quality",
        "biz_duplicate_document_group",
        "rel_duplicate_document_member",
        "biz_evidence_span",
        "biz_job_posting",
        "rel_job_posting_data_source",
        "biz_job_requirement",
        "rel_job_requirement_evidence",
        "biz_job_parse_run",
        "rel_job_parse_result",
        "biz_job_responsibility",
        "rel_job_fact_evidence",
        "md_technology_ambiguity_rule",
        "biz_technology_match_assessment",
        "biz_job_cluster_feature_snapshot",
    }.issubset(set(inspector.get_table_names()))

    command.downgrade(config, "base")
    inspector = inspect(create_engine(f"sqlite+pysqlite:///{database_path.as_posix()}"))
    assert inspector.get_table_names() == ["alembic_version"]
