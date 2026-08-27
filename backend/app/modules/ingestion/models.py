from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

primary_key_type = BigInteger().with_variant(Integer, "sqlite")


class RawFileAsset(Base):
    __tablename__ = "raw_file_asset"

    file_asset_id: Mapped[int] = mapped_column(primary_key_type, primary_key=True)
    asset_code: Mapped[str] = mapped_column(String(64), unique=True)
    asset_type_code: Mapped[str] = mapped_column(String(32))
    storage_object_key: Mapped[str] = mapped_column(String(1500))
    original_file_name: Mapped[str | None] = mapped_column(String(500))
    mime_type: Mapped[str | None] = mapped_column(String(200))
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    sha256_hash: Mapped[str] = mapped_column(String(64))
    virus_scan_status_code: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("sha256_hash", "asset_type_code", name="uk_file_asset_hash_type"),
    )


class FileImportRun(Base):
    __tablename__ = "biz_file_import_run"

    file_import_run_id: Mapped[int] = mapped_column(primary_key_type, primary_key=True)
    import_run_code: Mapped[str] = mapped_column(String(64), unique=True)
    file_asset_id: Mapped[int] = mapped_column(ForeignKey("raw_file_asset.file_asset_id"))
    importer_code: Mapped[str] = mapped_column(String(64))
    mapping_code: Mapped[str] = mapped_column(String(64))
    mapping_version: Mapped[str] = mapped_column(String(32))
    source_schema_hash: Mapped[str] = mapped_column(String(64))
    idempotency_key: Mapped[str] = mapped_column(String(64), unique=True)
    import_status_code: Mapped[str] = mapped_column(String(32), default="pending")
    total_row_count: Mapped[int] = mapped_column(Integer, default=0)
    success_row_count: Mapped[int] = mapped_column(Integer, default=0)
    skipped_row_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_row_count: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    error_summary_json: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("idx_file_import_status", "import_status_code", "created_at"),
        Index("idx_file_import_asset", "file_asset_id", "created_at"),
    )


class SpreadsheetRow(Base):
    __tablename__ = "raw_spreadsheet_row"

    spreadsheet_row_id: Mapped[int] = mapped_column(primary_key_type, primary_key=True)
    file_asset_id: Mapped[int] = mapped_column(ForeignKey("raw_file_asset.file_asset_id"))
    sheet_name: Mapped[str] = mapped_column(String(255))
    source_row_number: Mapped[int] = mapped_column(Integer)
    external_record_key: Mapped[str | None] = mapped_column(String(500))
    header_schema_hash: Mapped[str] = mapped_column(String(64))
    row_content_hash: Mapped[str] = mapped_column(String(64))
    row_payload_json: Mapped[dict] = mapped_column(JSON)
    access_classification_code: Mapped[str] = mapped_column(String(32), default="project_internal")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint(
            "file_asset_id",
            "sheet_name",
            "source_row_number",
            name="uk_spreadsheet_source_row",
        ),
        Index("idx_spreadsheet_row_hash", "row_content_hash"),
        Index("idx_spreadsheet_external_key", "external_record_key"),
    )


class FileImportRowResult(Base):
    __tablename__ = "biz_file_import_row_result"

    import_row_result_id: Mapped[int] = mapped_column(primary_key_type, primary_key=True)
    file_import_run_id: Mapped[int] = mapped_column(
        ForeignKey("biz_file_import_run.file_import_run_id")
    )
    spreadsheet_row_id: Mapped[int] = mapped_column(
        ForeignKey("raw_spreadsheet_row.spreadsheet_row_id")
    )
    row_status_code: Mapped[str] = mapped_column(String(32))
    target_type_code: Mapped[str | None] = mapped_column(String(64))
    target_record_key: Mapped[str | None] = mapped_column(String(128))
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_field: Mapped[str | None] = mapped_column(String(255))
    error_message: Mapped[str | None] = mapped_column(Text)
    normalized_payload_json: Mapped[dict | None] = mapped_column(JSON)
    replay_of_result_id: Mapped[int | None] = mapped_column(
        ForeignKey("biz_file_import_row_result.import_row_result_id")
    )
    processed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint(
            "file_import_run_id",
            "spreadsheet_row_id",
            name="uk_import_run_source_row",
        ),
        Index("idx_import_row_status", "file_import_run_id", "row_status_code"),
        Index("idx_import_row_target", "target_type_code", "target_record_key"),
    )
