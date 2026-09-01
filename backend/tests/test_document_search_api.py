"""原始文档检索接口：JD 与论文同表，检索只有一套实现。

年份过滤走 SQLAlchemy 的 `extract`，而不是 MySQL 的 `year()`——测试跑在内存 SQLite
上，方言相关的函数会直接报错，这条边界值得由测试守住。
"""

import hashlib
from datetime import datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.modules.job.models import DataSource, SourceDocument, SourceDocumentVersion


def _seed(session: Session) -> None:
    paper_source = DataSource(
        source_code="arxiv_test",
        source_name="arXiv 测试语料",
        source_type_code="corpus",
        content_type_code="paper_abstract",
        default_reliability_score=80,
        source_status_code="active",
    )
    job_source = DataSource(
        source_code="jd_test",
        source_name="JD 测试来源",
        source_type_code="recruitment",
        content_type_code="job",
        default_reliability_score=70,
        source_status_code="active",
    )
    session.add_all([paper_source, job_source])
    session.flush()

    fixtures = [
        (
            paper_source, "paper", "arxiv-1",
            "Dexterous Manipulation Survey", "grasping and manipulation",
            datetime(2024, 5, 1),
        ),
        (
            paper_source, "paper", "arxiv-2",
            "Legged Locomotion Control", "quadruped locomotion",
            datetime(2021, 3, 9),
        ),
        (job_source, "job", "job-1", "机器人算法工程师", "负责运动规划与抓取", None),
    ]
    for index, (source, doc_type, key, title, text, published) in enumerate(fixtures, start=1):
        document = SourceDocument(
            document_code=f"doc_test_{index}",
            data_source_id=source.data_source_id,
            document_type_code=doc_type,
            source_record_key=key,
            canonical_url=f"https://example.invalid/{key}",
            document_identity_key=f"identity-{key}",
            title=title,
            first_seen_at=datetime(2026, 1, 1),
            last_seen_at=datetime(2026, 1, 1),
        )
        session.add(document)
        session.flush()
        session.add(
            SourceDocumentVersion(
                source_document_id=document.source_document_id,
                version_no=1,
                published_at=published,
                collected_at=datetime(2026, 1, 1),
                valid_from=datetime(2026, 1, 1),
                content_text=text,
                content_json={"categories": ["cs.RO"], "primary_category": "cs.RO"},
                content_hash=hashlib.sha256(text.encode()).hexdigest(),
                is_current=True,
            )
        )
    session.commit()


def _client() -> tuple[TestClient, sessionmaker]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    with session_factory() as session:
        _seed(session)

    def override_db():
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    return TestClient(app), session_factory


def test_document_search_filters_by_type_text_and_year() -> None:
    client, _ = _client()
    try:
        with client:
            everything = client.get("/api/v1/documents").json()
            assert everything["total"] == 3

            papers = client.get("/api/v1/documents", params={"doc_type": "paper"}).json()
            assert papers["total"] == 2
            # 有发表日期的排前面，且按日期倒序。
            assert papers["items"][0]["source_record_key"] == "arxiv-1"

            # 正文命中：关键词只出现在摘要里，不在标题里。
            by_text = client.get("/api/v1/documents", params={"search": "quadruped"}).json()
            assert by_text["total"] == 1
            assert by_text["items"][0]["source_record_key"] == "arxiv-2"

            # 年份过滤必须在 SQLite 上也能跑通。
            in_2021 = client.get(
                "/api/v1/documents", params={"year_from": 2021, "year_to": 2021}
            ).json()
            assert in_2021["total"] == 1
            assert in_2021["items"][0]["source_record_key"] == "arxiv-2"

            # JD 没有发表日期，年份过滤应把它排除而不是报错。
            assert all(item["document_type_code"] == "paper" for item in in_2021["items"])
    finally:
        app.dependency_overrides.clear()


def test_document_facets_and_detail() -> None:
    client, _ = _client()
    try:
        with client:
            facets = client.get("/api/v1/documents/facets").json()
            assert facets["total"] == 3
            types = {entry["code"]: entry for entry in facets["types"]}
            assert types["paper"]["count"] == 2
            assert types["paper"]["label"] == "论文文献"
            assert types["job"]["count"] == 1
            # 只有带发表日期的文档进入年度分面。
            assert {entry["code"] for entry in facets["years"]} == {"2024", "2021"}

            detail = client.get("/api/v1/documents/doc_test_1").json()
            assert detail["title"] == "Dexterous Manipulation Survey"
            assert detail["content_text"] == "grasping and manipulation"
            assert detail["categories"] == ["cs.RO"]
            assert detail["version_no"] == 1

            assert client.get("/api/v1/documents/doc_missing").status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_milestone_search_filters_by_name() -> None:
    """搜索框对里程碑一直是启用的，但后端此前没有对应过滤，输入后没有任何反应。"""
    from app.modules.data_center.models import ExtractedFact, ExtractionRun, MilestoneEvent

    client, session_factory = _client()
    try:
        with session_factory() as session:
            # 里程碑必须挂在抽取事实上（extracted_fact_id 非空），因此先补最小的
            # 抽取运行 → 事实链路，复用夹具里已有的文档版本。
            run = ExtractionRun(
                run_code="run-test",
                source_document_version_id=1,
                extractor_code="test",
                extractor_version="1",
                input_hash="hash",
            )
            session.add(run)
            session.flush()
            facts = []
            for index in (1, 2):
                fact = ExtractedFact(
                    extraction_run_id=run.extraction_run_id,
                    fact_code=f"fact-{index}",
                    fact_type_code="milestone",
                    normalized_value_json={},
                    extraction_confidence_score=90,
                    publish_score=90,
                )
                session.add(fact)
                session.flush()
                facts.append(fact)
            session.add_all(
                [
                    MilestoneEvent(
                        milestone_code="MS-1",
                        extracted_fact_id=facts[0].extracted_fact_id,
                        milestone_name="人形机器人量产下线",
                        milestone_type_code="product",
                        event_year=2026,
                        description_text="量产里程碑",
                        verification_status_code="verified",
                    ),
                    MilestoneEvent(
                        milestone_code="MS-2",
                        extracted_fact_id=facts[1].extracted_fact_id,
                        milestone_name="视觉语言模型发布",
                        milestone_type_code="model",
                        event_year=2025,
                        description_text="多模态能力提升",
                        verification_status_code="verified",
                    ),
                ]
            )
            session.commit()

        with client:
            assert client.get("/api/v1/milestones").json()["total"] == 2
            hit = client.get("/api/v1/milestones", params={"search": "机器人"}).json()
            assert hit["total"] == 1
            assert hit["items"][0]["milestone_code"] == "MS-1"
            # 描述文本同样参与匹配。
            by_description = client.get("/api/v1/milestones", params={"search": "多模态"})
            assert by_description.json()["total"] == 1
    finally:
        app.dependency_overrides.clear()
