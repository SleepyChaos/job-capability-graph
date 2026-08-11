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
    }.issubset(set(inspector.get_table_names()))

    command.downgrade(config, "base")
    inspector = inspect(create_engine(f"sqlite+pysqlite:///{database_path.as_posix()}"))
    assert inspector.get_table_names() == ["alembic_version"]
