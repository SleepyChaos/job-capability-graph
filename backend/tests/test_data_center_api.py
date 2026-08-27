from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.modules.data_center.models import (
    AppUser,
    MilestoneTechnology,
    ReviewAction,
    ReviewTask,
)
from app.modules.job.models import EvidenceSpan
from app.modules.taxonomy.models import TechnologyNode, TechnologyTaxonomyVersion


def test_collection_to_milestone_review_closed_loop() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    with session_factory() as session:
        _seed_reviewer_and_technology(session)

    def override_db():
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as client:
            source = client.post(
                "/api/v1/sources",
                json={
                    "source_code": "SYNTH-OFFICIAL",
                    "source_name": "合成官方来源",
                    "source_type_code": "research",
                    "entry_url": "https://example.invalid/news",
                    "content_type_code": "milestone",
                    "authority_level_code": "official",
                    "independent_source_group": "synthetic-fixture",
                    "default_reliability_score": "90",
                },
            )
            assert source.status_code == 201

            policy = client.post(
                "/api/v1/collection-policies",
                json={
                    "source_code": "SYNTH-OFFICIAL",
                    "policy_version": "v1",
                    "max_depth": 1,
                    "robots_status_code": "allowed",
                    "terms_checked": True,
                    "allowed_scope_json": {"hosts": ["example.invalid"]},
                },
            )
            assert policy.status_code == 201

            run = client.post(
                "/api/v1/collection-runs",
                json={"source_code": "SYNTH-OFFICIAL", "policy_version": "v1"},
            )
            assert run.status_code == 201
            run_code = run.json()["run_code"]
            request = client.post(
                f"/api/v1/collection-runs/{run_code}/requests",
                json={
                    "request_url": "https://example.invalid/news/demo",
                    "request_depth": 1,
                    "request_type_code": "detail",
                },
            )
            assert request.status_code == 201

            payload = _synthetic_milestone_payload()
            candidate = client.post("/api/v1/milestones/candidates", json=payload)
            assert candidate.status_code == 201
            assert candidate.json()["verification_status_code"] == "candidate"
            milestone_code = candidate.json()["milestone_code"]

            # Identical material is idempotent and never creates a second candidate.
            duplicate = client.post("/api/v1/milestones/candidates", json=payload)
            assert duplicate.status_code == 201
            assert duplicate.json()["milestone_code"] == milestone_code

            reviews = client.get("/api/v1/reviews/data?status=queued")
            assert reviews.status_code == 200
            assert len(reviews.json()) == 1
            task_code = reviews.json()[0]["task_code"]
            assert "high_impact_fact_manual_review" in reviews.json()[0]["reason"]["codes"]

            unauthenticated = client.post(
                f"/api/v1/reviews/data/{task_code}/actions",
                json={"action_code": "approve"},
            )
            assert unauthenticated.status_code == 401
            approved = client.post(
                f"/api/v1/reviews/data/{task_code}/actions",
                headers={"X-Reviewer-Code": "reviewer-demo"},
                json={"action_code": "approve", "comment_text": "合成闭环验收通过"},
            )
            assert approved.status_code == 200
            assert approved.json()["verification_status_code"] == "verified"

            # One source document may support more than one distinct milestone fact.
            second_payload = _synthetic_milestone_payload()
            second_payload["milestone_name"] = "合成技术量产准备"
            second_payload["description_text"] = "同一材料中的另一条合成候选事实。"
            second = client.post("/api/v1/milestones/candidates", json=second_payload)
            assert second.status_code == 201
            assert second.json()["milestone_code"] != milestone_code

        with session_factory() as session:
            evidence = session.scalar(select(EvidenceSpan))
            assert evidence is not None
            content = _synthetic_milestone_payload()["content_text"]
            assert content[evidence.start_offset : evidence.end_offset] == evidence.evidence_text
            relation = session.scalar(select(MilestoneTechnology))
            assert relation is not None and relation.is_human_confirmed is True
            assert session.scalar(select(func.count()).select_from(EvidenceSpan)) == 1
            assert session.scalar(select(func.count()).select_from(ReviewTask)) == 2
            assert session.scalar(select(func.count()).select_from(ReviewAction)) == 1
    finally:
        app.dependency_overrides.clear()


def test_milestone_rejects_evidence_not_present_in_source() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    with session_factory() as session:
        _seed_reviewer_and_technology(session)

    def override_db():
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as client:
            client.post(
                "/api/v1/sources",
                json={
                    "source_code": "SYNTH-OFFICIAL",
                    "source_name": "合成官方来源",
                    "source_type_code": "research",
                    "content_type_code": "milestone",
                    "default_reliability_score": "90",
                },
            )
            payload = _synthetic_milestone_payload()
            payload["evidence_quote"] = "这段话并不存在于正文"
            response = client.post("/api/v1/milestones/candidates", json=payload)
            assert response.status_code == 422
            assert "证据原文" in response.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def _seed_reviewer_and_technology(session: Session) -> None:
    version = TechnologyTaxonomyVersion(
        version_code="synthetic-v1",
        version_name="合成测试分类",
        source_file_asset_id=1,
        effective_date=date(2026, 8, 11),
        version_status_code="active",
    )
    session.add(version)
    session.flush()
    session.add(
        TechnologyNode(
            taxonomy_version_id=version.taxonomy_version_id,
            technology_code="SYNTH-L2-001",
            source_spreadsheet_row_id=1,
            level_code="L2",
            technology_name="合成具身技术点",
            normalized_name="合成具身技术点",
        )
    )
    session.add(
        AppUser(
            user_code="reviewer-demo",
            display_name="合成审核员",
            role_code="reviewer",
        )
    )
    session.commit()


def _synthetic_milestone_payload() -> dict:
    quote = "合成具身技术点完成公开验证并进入试生产阶段"
    return {
        "data_source_code": "SYNTH-OFFICIAL",
        "source_record_key": "synthetic-milestone-001",
        "canonical_url": "https://example.invalid/news/demo",
        "title": "合成里程碑测试材料",
        "content_text": f"本材料仅用于系统集成测试。{quote}。不得作为真实行业数据使用。",
        "published_at": "2026-08-01T09:00:00",
        "collected_at": "2026-08-11T09:00:00",
        "milestone_name": "合成技术试生产",
        "milestone_type_code": "validation",
        "event_date": "2026-08-01",
        "event_year": 2026,
        "description_text": "用于验证候选、证据和审核状态流转的合成事件。",
        "maturity_delta_score": "15",
        "evidence_quote": quote,
        "technology_codes": ["SYNTH-L2-001"],
    }
