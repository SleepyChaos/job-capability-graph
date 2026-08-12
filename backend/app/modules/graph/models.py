from datetime import date, datetime

from sqlalchemy import Date, DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.modules.ingestion.models import primary_key_type

# technology_node_id 为 0 表示该行为技术域聚合行（跨技术去重），非 0 表示单技术行。
DOMAIN_AGGREGATE_TECHNOLOGY_ID = 0


class TechnologyDailyTriggerMetric(Base):
    """按日技术触发指标（后端设计 §11.4）。

    trigger_document_count 按"文档×技术×日"去重；域聚合行按域内全部技术去重。
    """

    __tablename__ = "biz_technology_daily_trigger_metric"

    technology_daily_trigger_metric_id: Mapped[int] = mapped_column(
        primary_key_type, primary_key=True
    )
    metric_date: Mapped[date] = mapped_column(Date)
    technology_domain_code: Mapped[str] = mapped_column(String(8))
    technology_node_id: Mapped[int] = mapped_column(Integer, default=0)
    trigger_document_count: Mapped[int] = mapped_column(Integer, default=0)
    trigger_mention_count: Mapped[int] = mapped_column(Integer, default=0)
    independent_org_count: Mapped[int] = mapped_column(Integer, default=0)
    independent_source_count: Mapped[int] = mapped_column(Integer, default=0)
    clustering_run_code: Mapped[str] = mapped_column(String(64))
    calculation_version: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint(
            "metric_date",
            "technology_domain_code",
            "technology_node_id",
            "clustering_run_code",
            name="uk_daily_trigger_metric",
        ),
    )
