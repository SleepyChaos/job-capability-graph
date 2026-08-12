import time
from uuid import uuid4

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.modules.data_center.models import CollectionRun, SourceCollectionPolicy
from app.modules.ingestion import web_crawler
from app.modules.job.models import DataSource, SourceDocument


def _setup_db() -> Session:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return Session(engine, expire_on_commit=False)


def _seed(session: Session) -> tuple[DataSource, SourceCollectionPolicy]:
    source = DataSource(
        source_code="web_test",
        source_name="网页采集测试源",
        source_type_code="enterprise",
        entry_url="http://example.test/list",
        content_type_code="mixed",
    )
    session.add(source)
    session.flush()
    policy = SourceCollectionPolicy(
        data_source_id=source.data_source_id,
        policy_version="v1",
        robots_status_code="allowed",
        rate_limit_per_minute=600,
    )
    session.add(policy)
    session.flush()
    return source, policy


def _new_run(session: Session, source: DataSource, policy: SourceCollectionPolicy) -> CollectionRun:
    run = CollectionRun(
        run_code=f"CR-{uuid4().hex[:12]}",
        data_source_id=source.data_source_id,
        collection_policy_id=policy.collection_policy_id,
        run_status_code="pending",
    )
    session.add(run)
    session.flush()
    return run


def test_extract_links_same_host_dedup() -> None:
    html = """
    <a href="/job/1">岗位一</a>
    <a href="http://example.test/job/1#anchor">重复</a>
    <a href="http://other.test/job/2">外站</a>
    <a href="javascript:void(0)">脚本</a>
    <a href="/job/2">岗位二</a>
    """
    links = web_crawler.extract_links(html, "http://example.test/list")
    assert links == ["http://example.test/job/1", "http://example.test/job/2"]


def test_extract_title_and_decode() -> None:
    assert web_crawler._extract_title("<title>  测试 标题 </title>") == "测试 标题"
    assert web_crawler._extract_title("<html></html>") is None
    assert web_crawler._decode_html("中文".encode("gbk")) == "中文"


def test_run_web_collection_increment_and_missing(monkeypatch) -> None:
    monkeypatch.setattr(time, "sleep", lambda _seconds: None)
    pages = {
        "http://example.test/list": ["/job/1", "/job/2"],
        "http://example.test/job/1": "岗位一内容版本A，机器人工程师招聘中。",
        "http://example.test/job/2": "岗位二内容版本A，感知工程师招聘中。",
    }

    def fake_fetch(url: str) -> tuple[int, bytes]:
        if url.endswith("/list"):
            body = "".join(f'<a href="{link}">x</a>' for link in pages[url])
            return 200, body.encode("utf-8")
        return 200, pages[url].encode("utf-8")

    monkeypatch.setattr(web_crawler, "fetch_url", fake_fetch)

    session = _setup_db()
    source, policy = _seed(session)

    first = web_crawler.run_web_collection(
        session, run=_new_run(session, source, policy), source=source, policy=policy
    )
    session.commit()
    assert (first.discovered_count, first.changed_count, first.unchanged_count) == (2, 0, 0)
    assert first.run_status_code == "success"

    # 第二次：job/1 未变、job/2 变化、job/3 新增
    pages["http://example.test/list"] = ["/job/1", "/job/2", "/job/3"]
    pages["http://example.test/job/2"] = "岗位二内容版本B，感知工程师招聘中（更新）。"
    pages["http://example.test/job/3"] = "岗位三内容，控制工程师招聘中。"
    second = web_crawler.run_web_collection(
        session, run=_new_run(session, source, policy), source=source, policy=policy
    )
    session.commit()
    assert (second.discovered_count, second.changed_count, second.unchanged_count) == (1, 1, 1)

    # 第三次：job/2、job/3 从列表消失 → missing_once
    pages["http://example.test/list"] = ["/job/1"]
    third = web_crawler.run_web_collection(
        session, run=_new_run(session, source, policy), source=source, policy=policy
    )
    session.commit()
    assert third.unchanged_count == 1
    statuses = {
        document.canonical_url: document.document_status_code
        for document in session.scalars(
            select(SourceDocument).where(SourceDocument.data_source_id == source.data_source_id)
        )
    }
    assert statuses["http://example.test/job/1"] == "active"
    assert statuses["http://example.test/job/2"] == "missing_once"
    assert statuses["http://example.test/job/3"] == "missing_once"

    # 第四次仍消失 → suspected_expired（设计 §5.3 连续消失判定）
    web_crawler.run_web_collection(
        session, run=_new_run(session, source, policy), source=source, policy=policy
    )
    session.commit()
    final_statuses = {
        document.canonical_url: document.document_status_code
        for document in session.scalars(
            select(SourceDocument).where(SourceDocument.data_source_id == source.data_source_id)
        )
    }
    assert final_statuses["http://example.test/job/2"] == "suspected_expired"
    assert final_statuses["http://example.test/job/1"] == "active"
    session.close()


def test_disallowed_policy_rejected(monkeypatch) -> None:
    monkeypatch.setattr(time, "sleep", lambda _seconds: None)
    session = _setup_db()
    source, policy = _seed(session)
    policy.robots_status_code = "disallowed"
    session.flush()
    try:
        web_crawler.run_web_collection(
            session, run=_new_run(session, source, policy), source=source, policy=policy
        )
        raise AssertionError("应当拒绝 robots disallowed 的采集")
    except ValueError as exc:
        assert "disallowed" in str(exc)
    session.close()
