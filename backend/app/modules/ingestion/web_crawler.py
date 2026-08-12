"""真实网页采集最小闭环（总体设计 §7、后端设计 §5）。

P1 范围：
- 仅使用标准库 urllib，尊重 User-Agent 标识与限速；
- 列表/入口页 → 详情页只深入一层，单次运行最多 MAX_DETAIL_PAGES 个详情页；
- 内容哈希增量判断：未变化仅更新 last_seen；变化创建新版本；
- 连续消失计数：missing_once → suspected_expired（设计 §5.3，来源访问失败不计数）；
- robots 状态为 disallowed 的策略拒绝执行。

网页仅保存快照与原文；JD/里程碑抽取由后续解析任务处理。
"""

from __future__ import annotations

import hashlib
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from html.parser import HTMLParser

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.data_center.models import CollectionRequest, CollectionRun, SourceCollectionPolicy
from app.modules.data_center.service import DataCenterError, record_collection_request
from app.modules.job.models import DataSource, SourceDocument, SourceDocumentVersion

USER_AGENT = "JobCapabilityGraphResearchBot/1.0 (challenge-cup research; polite crawler)"
MAX_DETAIL_PAGES = 20
MAX_PAGE_BYTES = 2 * 1024 * 1024
FETCH_TIMEOUT = 15
SUSPECTED_EXPIRED_AFTER = 2
PARSER_VERSION = "html_snapshot_v1"


class _LinkExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        for name, value in attrs:
            if name == "href" and value:
                self.links.append(value)


def fetch_url(url: str) -> tuple[int, bytes]:
    request = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"}
    )
    with urllib.request.urlopen(request, timeout=FETCH_TIMEOUT) as response:
        return response.status, response.read(MAX_PAGE_BYTES)


def extract_links(html: str, base_url: str) -> list[str]:
    parser = _LinkExtractor()
    try:
        parser.feed(html)
    except Exception:  # noqa: BLE001 - 容错解析，忽略畸形 HTML
        pass
    base_host = urllib.parse.urlparse(base_url).netloc
    seen: set[str] = set()
    result: list[str] = []
    for href in parser.links:
        absolute = urllib.parse.urljoin(base_url, href.strip())
        parsed = urllib.parse.urlparse(absolute)
        if parsed.scheme not in {"http", "https"} or parsed.netloc != base_host:
            continue
        normalized = urllib.parse.urlunparse(parsed._replace(fragment=""))
        if normalized in seen or normalized == base_url:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _decode_html(content: bytes) -> str:
    for encoding in ("utf-8", "gbk"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace")


def run_web_collection(
    db: Session, *, run: CollectionRun, source: DataSource, policy: SourceCollectionPolicy
) -> CollectionRun:
    if policy.robots_status_code == "disallowed":
        raise DataCenterError("robots 状态为 disallowed，拒绝执行采集")
    if not source.entry_url:
        raise DataCenterError("数据源缺少入口 URL，无法采集")

    run.run_status_code = "running"
    run.started_at = datetime.now()
    db.flush()

    interval = 60.0 / max(1, policy.rate_limit_per_minute)
    discovered = changed = unchanged = failed = 0
    observed_document_ids: set[int] = set()
    entry_success = False

    entry_request = record_collection_request(
        db, run=run, request_url=source.entry_url, request_depth=0, request_type_code="entry"
    )
    entry_html = ""
    try:
        status, content = fetch_url(source.entry_url)
        entry_html = _decode_html(content)
        _complete_request(db, entry_request, status, content)
        entry_success = True
    except (urllib.error.URLError, OSError, ValueError) as exc:
        _fail_request(db, entry_request, str(exc))
        failed += 1

    if entry_success:
        links = extract_links(entry_html, source.entry_url)[:MAX_DETAIL_PAGES]
        for index, link in enumerate(links):
            if index:
                time.sleep(interval)
            detail_request = record_collection_request(
                db,
                run=run,
                request_url=link,
                request_depth=1,
                request_type_code="detail",
                parent_request_id=entry_request.collection_request_id,
            )
            try:
                status, content = fetch_url(link)
            except (urllib.error.URLError, OSError, ValueError) as exc:
                _fail_request(db, detail_request, str(exc))
                failed += 1
                continue
            _complete_request(db, detail_request, status, content)
            outcome = _upsert_document(
                db,
                run=run,
                source=source,
                url=link,
                content=content,
                title=_extract_title(_decode_html(content)),
            )
            observed_document_ids.add(outcome[0])
            if outcome[1] == "discovered":
                discovered += 1
            elif outcome[1] == "changed":
                changed += 1
            else:
                unchanged += 1

    if entry_success:
        _mark_missing_documents(db, source, observed_document_ids)

    run.discovered_count = discovered
    run.changed_count = changed
    run.unchanged_count = unchanged
    run.failed_count = failed
    run.completed_at = datetime.now()
    run.run_status_code = "success" if entry_success else "failed"
    if not entry_success:
        run.error_summary = "入口页访问失败，本次运行未产生增量判断。"
    db.flush()
    return run


def _complete_request(
    db: Session, request: CollectionRequest, status: int, content: bytes
) -> None:
    request.request_status_code = "success"
    request.response_status_code = status
    request.response_content_hash = hashlib.sha256(content).hexdigest()
    request.completed_at = datetime.now()
    request.requested_at = request.requested_at or request.completed_at
    db.flush()


def _fail_request(db: Session, request: CollectionRequest, message: str) -> None:
    request.request_status_code = "failed"
    request.error_message = message[:2000]
    request.completed_at = datetime.now()
    request.requested_at = request.requested_at or request.completed_at
    db.flush()


def _extract_title(html: str) -> str | None:
    match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    return re.sub(r"\s+", " ", match.group(1)).strip()[:1000] or None


def _upsert_document(
    db: Session,
    *,
    run: CollectionRun,
    source: DataSource,
    url: str,
    content: bytes,
    title: str | None,
) -> tuple[int, str]:
    identity = hashlib.sha256(f"{source.source_code}\0{url}".encode()).hexdigest()
    content_hash = hashlib.sha256(content).hexdigest()
    now = datetime.now()
    document = db.scalar(
        select(SourceDocument).where(
            SourceDocument.data_source_id == source.data_source_id,
            SourceDocument.document_identity_key == identity,
        )
    )
    if document is None:
        document = SourceDocument(
            document_code=f"DOC-W-{identity[:20]}",
            data_source_id=source.data_source_id,
            document_type_code="web_page",
            canonical_url=url,
            document_identity_key=identity,
            title=title,
            first_seen_at=now,
            last_seen_at=now,
        )
        db.add(document)
        db.flush()
        _add_version(db, document, run, content, content_hash, title, url, now, version_no=1)
        return document.source_document_id, "discovered"

    document.last_seen_at = now
    document.missing_successive_runs = 0
    document.document_status_code = "active"
    if title:
        document.title = title
    current = db.scalar(
        select(SourceDocumentVersion).where(
            SourceDocumentVersion.source_document_id == document.source_document_id,
            SourceDocumentVersion.is_current.is_(True),
        )
    )
    if current is not None and current.content_hash == content_hash:
        return document.source_document_id, "unchanged"
    _add_version(
        db,
        document,
        run,
        content,
        content_hash,
        title,
        url,
        now,
        version_no=(current.version_no + 1) if current else 1,
        previous_version_id=current.source_document_version_id if current else None,
    )
    if current is not None:
        current.is_current = False
        current.valid_to = now
    return document.source_document_id, "changed"


def _add_version(
    db: Session,
    document: SourceDocument,
    run: CollectionRun,
    content: bytes,
    content_hash: str,
    title: str | None,
    url: str,
    now: datetime,
    *,
    version_no: int,
    previous_version_id: int | None = None,
) -> None:
    db.add(
        SourceDocumentVersion(
            source_document_id=document.source_document_id,
            collection_run_id=run.collection_run_id,
            version_no=version_no,
            previous_version_id=previous_version_id,
            collected_at=now,
            valid_from=now,
            content_text=_decode_html(content)[:200_000],
            content_json={"url": url, "title": title, "bytes": len(content)},
            content_hash=content_hash,
            parser_version=PARSER_VERSION,
            is_current=True,
        )
    )
    db.flush()


def _mark_missing_documents(
    db: Session, source: DataSource, observed_document_ids: set[int]
) -> None:
    documents = db.scalars(
        select(SourceDocument).where(
            SourceDocument.data_source_id == source.data_source_id,
            SourceDocument.document_type_code == "web_page",
            SourceDocument.document_status_code.in_(["active", "missing_once"]),
        )
    )
    for document in documents:
        if document.source_document_id in observed_document_ids:
            continue
        document.missing_successive_runs += 1
        if document.missing_successive_runs >= SUSPECTED_EXPIRED_AFTER:
            document.document_status_code = "suspected_expired"
        else:
            document.document_status_code = "missing_once"
