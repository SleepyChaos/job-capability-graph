"""按指定词表版本对既有 JD 重跑技术词抽取（窗口 C 换版链路）。

背景：技术词表面匹配原本只在 JD 导入时执行一次，词表升版后没有任何入口能在既有
语料上重新抽取。本工具用 `extract_requirements` 在同一批 JD 上按新版词表再抽一遍，
产出按 `taxonomy_version_id` 归属，v1.1 的抽取结果与历史解析运行不受影响。

幂等：目标版本已有抽取结果时默认直接返回既有统计；`--replace` 会先删除该版本的
抽取结果再重建（只删本版本的行，其它版本不动）。

用法（backend 目录 / 容器内）：
    python -m tools.reextract_requirements --taxonomy-version v1.2
    python -m tools.reextract_requirements --taxonomy-version v1.2 --replace
"""

from __future__ import annotations

import argparse
import json

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.modules.job.extraction_service import build_alias_matcher, extract_requirements
from app.modules.job.models import (
    JobPosting,
    JobRequirement,
    JobRequirementEvidence,
    SourceDocumentVersion,
)
from app.modules.taxonomy.models import TechnologyTaxonomyVersion


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="按指定词表版本对既有JD重跑技术词抽取。")
    parser.add_argument("--taxonomy-version", required=True)
    parser.add_argument(
        "--replace",
        action="store_true",
        help="目标版本已有抽取结果时先清空再重建（只影响该词表版本）。",
    )
    parser.add_argument("--batch-size", type=int, default=200)
    return parser.parse_args()


def existing_count(session: Session, taxonomy_version_id: int) -> int:
    return (
        session.scalar(
            select(func.count())
            .select_from(JobRequirement)
            .where(JobRequirement.taxonomy_version_id == taxonomy_version_id)
        )
        or 0
    )


def purge_version(session: Session, taxonomy_version_id: int) -> None:
    """删除该词表版本下的技术要求与关联行；证据跨度按哈希共享，保留不删。"""
    requirement_ids = list(
        session.scalars(
            select(JobRequirement.job_requirement_id).where(
                JobRequirement.taxonomy_version_id == taxonomy_version_id
            )
        )
    )
    for start in range(0, len(requirement_ids), 1000):
        chunk = requirement_ids[start : start + 1000]
        session.execute(
            delete(JobRequirementEvidence).where(
                JobRequirementEvidence.job_requirement_id.in_(chunk)
            )
        )
        session.execute(
            delete(JobRequirement).where(JobRequirement.job_requirement_id.in_(chunk))
        )
    session.commit()


def main() -> None:
    args = parse_args()
    with SessionLocal() as session:
        taxonomy = session.scalar(
            select(TechnologyTaxonomyVersion).where(
                TechnologyTaxonomyVersion.version_code == args.taxonomy_version
            )
        )
        if taxonomy is None:
            raise SystemExit(f"词表版本不存在：{args.taxonomy_version}")
        already = existing_count(session, taxonomy.taxonomy_version_id)
        if already and not args.replace:
            print(
                json.dumps(
                    {
                        "version_code": taxonomy.version_code,
                        "requirement_count": already,
                        "already_extracted": True,
                    },
                    ensure_ascii=False,
                )
            )
            return
        if already:
            purge_version(session, taxonomy.taxonomy_version_id)

        matcher = build_alias_matcher(session, taxonomy.taxonomy_version_id)
        jobs = list(session.scalars(select(JobPosting).order_by(JobPosting.job_posting_id)))
        versions = {
            item.source_document_version_id: item
            for item in session.scalars(select(SourceDocumentVersion))
        }
        requirement_total = 0
        evidence_total = 0
        jobs_with_evidence = 0
        for index, job in enumerate(jobs, start=1):
            counts = extract_requirements(
                session,
                job=job,
                document_version=versions[job.source_document_version_id],
                matcher=matcher,
                taxonomy_version_id=taxonomy.taxonomy_version_id,
            )
            requirement_total += counts.requirement_count
            evidence_total += counts.evidence_count
            jobs_with_evidence += 1 if counts.requirement_count else 0
            if index % args.batch_size == 0:
                session.commit()
        session.commit()
    print(
        json.dumps(
            {
                "version_code": args.taxonomy_version,
                "pattern_count": len(matcher.patterns),
                "job_count": len(jobs),
                "job_with_requirement_count": jobs_with_evidence,
                "requirement_count": requirement_total,
                "evidence_link_count": evidence_total,
                "already_extracted": False,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
