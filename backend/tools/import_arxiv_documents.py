"""把 arXiv 上游语料落成正式的原始文档，供文献检索使用。

**为什么现在才入库。** `fetch_arxiv_corpus.py` 只把论文落到 `data/upstream/arxiv/`
的 JSONL 里，那个目录按体积原因不入库；抽取链路（`extract_upstream_technologies`）
直接读文件，所以此前没有入库的必要。但文献检索是给人用的查询界面，不能依赖一个
克隆仓库后并不存在的目录——因此这里把论文写进 `raw_source_document`，与 JD 文档
共用同一张表和同一套版本语义。

**与 JD 文档同表而不另起一张。** 两者都是「某个来源在某个时间点提供的一份文档」，
差别只在 `document_type_code`（job / paper）。同表带来的直接好处是检索接口只需要
一个实现，数据管理中心的「原始文档」标签页也就同时拿到了两类数据。

**幂等。** 以 `sha256(source_code\\0arxiv_id)` 作为 `document_identity_key`，与 JD
侧 `import_jobs` 的做法一致；重复执行只更新 `last_seen_at`，不产生重复行。摘要写进
版本表的 `content_text`，分类写 `content_json`，`published_at` 用论文自带的发表日期
——它是文档属性而非采集产物，是上游语料里唯一干净的时间轴。

用法（backend 目录 / 容器内）：
    python -m tools.import_arxiv_documents --corpus-dir /srv/data/upstream/arxiv
    python -m tools.import_arxiv_documents --limit-per-year 200   # 只取每年前 200 篇
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.db.session import SessionLocal
from app.modules.job.models import DataSource, SourceDocument, SourceDocumentVersion
from app.modules.job.service import stable_code

SOURCE_CODE = "arxiv_embodied_ai"
SOURCE_NAME = "arXiv 具身智能上游语料"
DOCUMENT_TYPE = "paper"


def parse_date(value: object) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d")
    except ValueError:
        return None


def ensure_source(db) -> DataSource:
    source = db.scalar(select(DataSource).where(DataSource.source_code == SOURCE_CODE))
    if source is not None:
        return source
    source = DataSource(
        source_code=SOURCE_CODE,
        source_name=SOURCE_NAME,
        source_type_code="corpus",
        entry_url="https://arxiv.org",
        content_type_code="paper_abstract",
        authority_level_code="public_preprint",
        independent_source_group="arxiv",
        license_note="arXiv 摘要按 arXiv 使用条款检索获得，仅保留题录与摘要。",
        source_status_code="active",
    )
    db.add(source)
    db.flush()
    return source


def iter_papers(corpus_dir: Path, limit_per_year: int | None):
    for path in sorted(corpus_dir.glob("*.jsonl")):
        taken = 0
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                if limit_per_year is not None and taken >= limit_per_year:
                    break
                taken += 1
                yield json.loads(line)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus-dir", default="/srv/data/upstream/arxiv")
    parser.add_argument("--limit-per-year", type=int, default=None)
    args = parser.parse_args()

    corpus_dir = Path(args.corpus_dir)
    if not corpus_dir.exists():
        raise SystemExit(f"语料目录不存在：{corpus_dir}")

    now = datetime.now(UTC).replace(tzinfo=None)
    created = 0
    refreshed = 0
    skipped_no_id = 0

    with SessionLocal() as db:
        source = ensure_source(db)
        existing = {
            key
            for (key,) in db.execute(
                select(SourceDocument.document_identity_key).where(
                    SourceDocument.data_source_id == source.data_source_id
                )
            )
        }

        for paper in iter_papers(corpus_dir, args.limit_per_year):
            arxiv_id = str(paper.get("arxiv_id") or "").strip()
            if not arxiv_id:
                skipped_no_id += 1
                continue
            identity = hashlib.sha256(f"{SOURCE_CODE}\0{arxiv_id}".encode()).hexdigest()
            if identity in existing:
                refreshed += 1
                continue

            title = str(paper.get("title") or "").strip()[:1000]
            abstract = str(paper.get("abstract") or "").strip()
            published = parse_date(paper.get("published"))
            document = SourceDocument(
                document_code=stable_code("doc", identity),
                data_source_id=source.data_source_id,
                document_type_code=DOCUMENT_TYPE,
                source_record_key=arxiv_id,
                canonical_url=f"https://arxiv.org/abs/{arxiv_id}",
                document_identity_key=identity,
                title=title,
                first_seen_at=now,
                last_seen_at=now,
            )
            db.add(document)
            db.flush()
            db.add(
                SourceDocumentVersion(
                    source_document_id=document.source_document_id,
                    version_no=1,
                    published_at=published,
                    collected_at=now,
                    source_collected_at=published,
                    valid_from=published or now,
                    content_text=abstract,
                    content_json={
                        "categories": paper.get("categories") or [],
                        "primary_category": paper.get("primary_category"),
                        "updated": paper.get("updated"),
                    },
                    content_hash=hashlib.sha256(abstract.encode()).hexdigest(),
                    parser_version="arxiv_jsonl_v1",
                    is_current=True,
                )
            )
            existing.add(identity)
            created += 1

        db.commit()

    print(
        json.dumps(
            {
                "source_code": SOURCE_CODE,
                "created": created,
                "already_present": refreshed,
                "skipped_without_id": skipped_no_id,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
