"""导出新岗位发现两条外部证据链路的测试数据（输入样例 + 输出原文）。

研究侧（`upstream_signal`）与产业侧（`milestone_signal`）走同一套算法，
差别只在证据来源，因此本脚本用同一段代码按候选编码分别导出，避免两份实现走偏。

导出的「输入」全部从运行库现场查回，不是手写样例：技术词主数据、招聘侧共现基线
（含反证查询：两技术同现的 JD 条数应为 0）、以及各自的证据源（论文语料 / 里程碑事件）。
「输出」是候选落库后的完整记录，含事实卡、表达层、标准 JD 与审核任务。

用法（在能连到运行库的容器内）：
    python export_test_chain.py /tmp/testchain
"""

from __future__ import annotations

import json
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import text

from app.db.session import SessionLocal

# 两条链路各取一条已走完全流程（已审批、已生成标准 JD）的候选。
#
# `corpus_terms` 只用于研究侧：候选落库时的抽取产物（JSONL）已不在数据目录中，
# 而这两个技术点在当前词表版本下没有登记别名，按中文技术名去匹配英文论文摘要
# 匹配不到任何东西。因此检索词由人工给出，并在导出结果里标注为重建样例——
# 它证明「这两个技术确实在论文里同现」，但不等同于当次运行的抽取输出。
CHAINS = {
    "research": {
        "candidate_code": "upstream_0576ac2ed00345c0b6d6",
        "label": "研究侧领先信号",
        "corpus_terms": {
            "T1.01.11": ["vision-language-action", "VLA "],
            "T1.09.01": ["dual-arm", "bimanual"],
        },
    },
    "industry": {
        "candidate_code": "milestone_5b063c8bbe6b441b986",
        "label": "产业里程碑信号",
    },
}


def encode(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    return value


def rows(session, sql: str, **params) -> list[dict]:
    result = session.execute(text(sql), params)
    keys = result.keys()
    return [{k: encode(v) for k, v in zip(keys, row, strict=True)} for row in result]


def dump(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {path}")


def taxonomy_version_of(session, node_ids: list[int]) -> dict:
    """候选所属的词表版本。

    库里 5 个版本的 `version_status_code` 全是 active，按状态筛会同时命中五版：
    一个技术点导出成五行，招聘侧命中数也会跨版本累加。候选的身份锚在它引用的
    节点 id 上，因此版本由标准 JD 引用的节点反查得到，而不是猜一个「当前版本」。
    """
    found = rows(
        session,
        """
        SELECT DISTINCT v.taxonomy_version_id, v.version_code, v.version_name,
               v.effective_date
        FROM md_technology_node n
        JOIN md_technology_taxonomy_version v ON v.taxonomy_version_id = n.taxonomy_version_id
        WHERE n.technology_node_id IN :ids
        """,
        ids=tuple(node_ids),
    )
    if len(found) != 1:
        raise SystemExit(f"候选引用的节点跨了多个词表版本：{found}")
    return found[0]


def technology_rows(session, codes: list[str], version_id: int) -> list[dict]:
    return rows(
        session,
        """
        SELECT n.technology_node_id, n.technology_code, n.technology_name, n.level_code,
               n.semantic_role_code, n.definition_text, n.governance_status_code,
               v.version_code, d.domain_code, d.domain_name
        FROM md_technology_node n
        JOIN md_technology_taxonomy_version v ON v.taxonomy_version_id = n.taxonomy_version_id
        -- 一个节点可挂多个技术域，只取主域，否则一个技术会导出成五行看似不同的记录。
        LEFT JOIN rel_technology_node_domain rd
               ON rd.technology_node_id = n.technology_node_id AND rd.is_primary = 1
        LEFT JOIN md_technology_domain d ON d.technology_domain_id = rd.technology_domain_id
        WHERE n.technology_code IN :codes AND n.taxonomy_version_id = :version_id
        """,
        codes=tuple(codes),
        version_id=version_id,
    )


def alias_rows(session, codes: list[str], version_id: int) -> list[dict]:
    return rows(
        session,
        """
        SELECT n.technology_code, a.alias_text, a.alias_type_code
        FROM md_technology_alias a
        JOIN md_technology_node n ON n.technology_node_id = a.technology_node_id
        JOIN md_technology_taxonomy_version v ON v.taxonomy_version_id = n.taxonomy_version_id
        WHERE n.technology_code IN :codes AND n.taxonomy_version_id = :version_id
        ORDER BY n.technology_code, a.alias_text
        """,
        codes=tuple(codes),
        version_id=version_id,
    )


# 招聘侧口径必须与缺口判定工具逐字一致，否则导出的「同现 JD 数」与候选卡上记录的
# 不是同一个量，会读出一个并不存在的矛盾。`find_upstream_only_pairs.load_jd` 取
# **某一次解析运行**中复核状态为 accepted 的技术命中，并按 technology_code 比较
# （不限词表版本——JD 侧与候选侧的版本本就不同，代码空间才是两边的公共坐标）。
#
# 解析运行必须显式指定，不能沿用「最近一次成功聚类」：那是个会漂移的锚。候选建于
# 2026-08-26，当时的最近一次是下面这条；此后又落了一次以 2026-08-10 为目标日的聚类
# （解析运行 12），用它复算会得到 T3.08.04 = 10 而非卡上的 108，看起来像证据消失了，
# 实际只是换了语料快照。
CLUSTERING_RUN_CODE = "cluster_8c34456a914d4e53bac8afa3"

JD_SCOPE = """
    JOIN biz_technology_match_assessment a ON a.job_requirement_id = r.job_requirement_id
    WHERE a.job_parse_run_id = (
              SELECT c.job_parse_run_id FROM biz_job_clustering_run c
              WHERE c.run_code = :clustering_run_code
          )
      AND a.assessment_status_code = 'accepted'
      AND n.technology_code IN :codes
"""


def jd_baseline(session, codes: list[str]) -> dict:
    """招聘侧共现基线。

    两条链路的立论前提都是「该组合在 JD 中从未同现」，因此这里不只导出各技术的
    命中量，还要把反证查询本身连同结果一起留下：同现 JD 数必须为 0。
    """
    per_technology = rows(
        session,
        f"""
        SELECT n.technology_code, n.technology_name,
               COUNT(DISTINCT r.job_posting_id) AS jd_count
        FROM biz_job_requirement r
        JOIN md_technology_node n ON n.technology_node_id = r.technology_node_id
        {JD_SCOPE}
        GROUP BY n.technology_code, n.technology_name
        """,
        codes=tuple(codes),
        clustering_run_code=CLUSTERING_RUN_CODE,
    )
    cooccurrence = rows(
        session,
        f"""
        SELECT COUNT(*) AS jd_with_both FROM (
            SELECT r.job_posting_id
            FROM biz_job_requirement r
            JOIN md_technology_node n ON n.technology_node_id = r.technology_node_id
            {JD_SCOPE}
            GROUP BY r.job_posting_id
            HAVING COUNT(DISTINCT n.technology_code) = :code_count
        ) t
        """,
        codes=tuple(codes),
        code_count=len(codes),
        clustering_run_code=CLUSTERING_RUN_CODE,
    )
    samples = rows(
        session,
        f"""
        SELECT n.technology_code, p.job_code, p.job_title_raw, p.company_name_raw,
               p.published_at, p.collected_at, p.time_quality_code,
               LEFT(r.raw_text, 160) AS requirement_excerpt
        FROM biz_job_requirement r
        JOIN md_technology_node n ON n.technology_node_id = r.technology_node_id
        JOIN biz_job_posting p ON p.job_posting_id = r.job_posting_id
        {JD_SCOPE}
        ORDER BY n.technology_code, p.job_posting_id
        LIMIT 12
        """,
        codes=tuple(codes),
        clustering_run_code=CLUSTERING_RUN_CODE,
    )
    return {
        "说明": f"招聘侧基线口径与 find_upstream_only_pairs.load_jd 一致："
        f"聚类运行 {CLUSTERING_RUN_CODE} 所属解析运行中复核状态 accepted 的技术命中，"
        f"按 technology_code 比较，不限词表版本。",
        "各技术命中 JD 数": per_technology,
        "同现 JD 数（缺口成立的前提，应为 0）": cooccurrence,
        "命中 JD 样例": samples,
    }


def upstream_evidence(session, codes: list[str], terms: dict[str, list[str]]) -> dict:
    """研究侧证据源：论文语料中同时命中两个技术的文档。

    落库的候选由离线抽取产物（JSONL）生成，那批文件已不在数据目录中，且这两个技术点
    在当前词表版本下没有登记别名，因此检索词由人工给出（见 CHAINS.corpus_terms）。
    导出结果标注为重建样例：它能证明两个技术确实在论文里同现，但不是当次运行的抽取输出。
    """
    left, right = codes
    left_clause = " OR ".join(
        f"v.content_text LIKE :l{i}" for i in range(len(terms[left]))
    )
    right_clause = " OR ".join(
        f"v.content_text LIKE :r{i}" for i in range(len(terms[right]))
    )
    params = {f"l{i}": f"%{term}%" for i, term in enumerate(terms[left])}
    params.update({f"r{i}": f"%{term}%" for i, term in enumerate(terms[right])})
    matched = rows(
        session,
        f"""
        SELECT d.document_code, d.title, d.canonical_url, v.published_at,
               LEFT(v.content_text, 600) AS abstract_excerpt
        FROM raw_source_document d
        JOIN raw_source_document_version v
             ON v.source_document_id = d.source_document_id AND v.is_current = 1
        WHERE d.document_type_code = 'paper'
          AND ({left_clause}) AND ({right_clause})
        ORDER BY v.published_at DESC
        LIMIT 5
        """,
        **params,
    )
    return {
        "说明": "重建样例：按人工给定的检索词在库内 13,282 篇论文全文上重新匹配，"
        "非当次运行的抽取输出文件。",
        "语料规模": rows(
            session,
            "SELECT COUNT(*) AS paper_count FROM raw_source_document "
            "WHERE document_type_code = 'paper'",
        ),
        "检索词": terms,
        "同时命中两个技术的论文": matched,
    }


def milestone_evidence(session, milestone_codes: list[str]) -> dict:
    events = rows(
        session,
        """
        SELECT m.milestone_code, m.milestone_name, m.milestone_type_code, m.event_date,
               m.event_year, m.description_text, m.verification_status_code,
               m.data_origin_code, m.maturity_delta_score
        FROM biz_milestone_event m
        WHERE m.milestone_code IN :codes
        """,
        codes=tuple(milestone_codes),
    )
    links = rows(
        session,
        """
        SELECT m.milestone_code, n.technology_code, n.technology_name,
               r.relation_type_code, r.relevance_score, r.is_human_confirmed
        FROM rel_milestone_technology r
        JOIN biz_milestone_event m ON m.milestone_event_id = r.milestone_event_id
        JOIN md_technology_node n ON n.technology_node_id = r.technology_node_id
        WHERE m.milestone_code IN :codes
        """,
        codes=tuple(milestone_codes),
    )
    evidence = rows(
        session,
        """
        SELECT m.milestone_code, s.evidence_text, s.span_type_code, d.document_code, d.title
        FROM rel_milestone_evidence r
        JOIN biz_milestone_event m ON m.milestone_event_id = r.milestone_event_id
        JOIN biz_evidence_span s ON s.evidence_span_id = r.evidence_span_id
        JOIN raw_source_document_version v
             ON v.source_document_version_id = s.source_document_version_id
        JOIN raw_source_document d ON d.source_document_id = v.source_document_id
        WHERE m.milestone_code IN :codes
        LIMIT 10
        """,
        codes=tuple(milestone_codes),
    )
    return {
        "说明": "产业侧证据源：里程碑事件本体、其技术链接与原文证据片段。",
        "里程碑事件": events,
        "事件技术链接": links,
        "原文证据片段": evidence,
    }


def candidate_output(session, candidate_code: str) -> dict:
    candidate = rows(
        session,
        """
        SELECT c.candidate_code, c.proposed_name, c.classification_code,
               c.maturity_stage_code, c.workflow_status_code, c.candidate_score,
               c.support_job_count, c.candidate_key, c.risk_flags_json,
               c.mechanical_card_json, c.expression_json, c.expression_model_version,
               c.nearest_job_role_id, c.overlap_score,
               c.approved_job_role_id, c.created_at, c.updated_at
        FROM biz_emerging_role_candidate c
        WHERE c.candidate_code = :code
        """,
        code=candidate_code,
    )
    run = rows(
        session,
        """
        SELECT r.run_code, r.mode_code, r.target_date, r.run_status_code, r.algorithm_version,
               r.input_snapshot_json, r.result_summary_json, r.started_at, r.completed_at
        FROM biz_role_discovery_run r
        JOIN biz_emerging_role_candidate c ON c.discovery_run_id = r.discovery_run_id
        WHERE c.candidate_code = :code
        """,
        code=candidate_code,
    )
    standard_jd = rows(
        session,
        """
        SELECT s.standard_jd_code, s.version_no, s.title_text, s.content_json,
               s.is_market_evidence, s.created_at
        FROM biz_standard_job_description s
        JOIN biz_emerging_role_candidate c
             ON c.emerging_role_candidate_id = s.emerging_role_candidate_id
        WHERE c.candidate_code = :code
        """,
        code=candidate_code,
    )
    review = rows(
        session,
        """
        SELECT t.task_code, t.queue_code, t.target_type_code, t.task_status_code,
               t.priority_score, t.reason_json, t.created_at, t.updated_at
        FROM biz_review_task t
        JOIN biz_emerging_role_candidate c
             ON c.emerging_role_candidate_id = t.target_id
        WHERE c.candidate_code = :code
          AND t.queue_code = 'job_discovery' AND t.target_type_code = 'emerging_role'
        """,
        code=candidate_code,
    )
    approved_role = rows(
        session,
        """
        SELECT jr.role_code, jr.canonical_name, jr.origin_type_code,
               jr.lifecycle_status_code, jr.first_detected_at, jr.approved_at
        FROM biz_job_role jr
        JOIN biz_emerging_role_candidate c ON c.approved_job_role_id = jr.job_role_id
        WHERE c.candidate_code = :code
        """,
        code=candidate_code,
    )
    return {
        "候选": candidate,
        "推演运行": run,
        "标准JD": standard_jd,
        "审核任务": review,
        "入库岗位": approved_role,
    }


def main() -> None:
    out_root = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/testchain")
    session = SessionLocal()
    try:
        for chain, meta in CHAINS.items():
            code = meta["candidate_code"]
            output = candidate_output(session, code)
            if not output["候选"]:
                raise SystemExit(f"候选不存在：{code}")
            card = output["候选"][0]["mechanical_card_json"]
            if isinstance(card, str):
                card = json.loads(card)
            tech_codes = list(card["technology_codes"])

            dump(out_root / "output" / f"{chain}_候选完整记录.json", output)

            jd_content = output["标准JD"][0]["content_json"]
            if isinstance(jd_content, str):
                jd_content = json.loads(jd_content)
            version = taxonomy_version_of(session, jd_content["technology_node_ids"])
            version_id = version["taxonomy_version_id"]

            nodes = technology_rows(session, tech_codes, version_id)
            aliases = alias_rows(session, tech_codes, version_id)
            dump(
                out_root / "input" / chain / "01_技术词主数据.json",
                {"词表版本": version, "技术节点": nodes, "别名": aliases},
            )
            dump(
                out_root / "input" / chain / "02_招聘侧共现基线.json",
                jd_baseline(session, tech_codes),
            )
            if chain == "research":
                dump(
                    out_root / "input" / chain / "03_论文语料证据.json",
                    upstream_evidence(session, tech_codes, meta["corpus_terms"]),
                )
            else:
                milestone_codes = [item["milestone_code"] for item in card.get("milestones", [])]
                dump(
                    out_root / "input" / chain / "03_里程碑事件证据.json",
                    milestone_evidence(session, milestone_codes),
                )
    finally:
        session.close()


if __name__ == "__main__":
    main()
