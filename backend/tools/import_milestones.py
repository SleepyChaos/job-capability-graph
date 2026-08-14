from __future__ import annotations

import argparse
import json
import re
import sqlite3
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select

from app.db.session import SessionLocal
from app.modules.data_center.models import MilestoneEvent, MilestoneTechnology
from app.modules.data_center.service import MilestoneSubmission, submit_milestone_candidate
from app.modules.job.models import DataSource
from app.modules.taxonomy.models import TechnologyNode, TechnologyTaxonomyVersion

# 旧实验库的中文事件类型 -> 本项目 EVENT_TYPE_WEIGHTS 的编码（discovery/algorithm.py）
EVENT_TYPE_MAP = {
    "企业事件": "enterprise_application",
    "平台/工具发布": "platform_release",
    "产品发布": "product_release",
    "开源发布": "open_source",
    "标准/政策": "standard_policy",
    "技术突破": "breakthrough",
    "论文发表": "paper",
    "技术演示": "technology_demo",
    "其他": "other",
}

# 人工补链接：47 条无 technology_links 的记录里，43 条属于"产业生态与企业事件"、4 条"其他"，
# 且这两个类别在全数据集中没有任何已链接样本可供反推。其中绝大多数是融资、IPO、收购、
# 高校共建、人物榜单一类的业务事件，给它们挂技术节点等于把融资新闻当成技术成熟度证据。
# 只补下面这批描述里含明确技术或落地场景的，其余保持不链接。
# 这些恰好落在此前统计出的未覆盖区（T7 应用场景、T3.08 芯片），对候选覆盖率的补益最大。
CURATED_TECHNOLOGY_LINKS: dict[str, list[list]] = {
    # 人形机器人量产与规模化交付
    "EVENT-0064": [["T3.01", 1.0]],  # Figure BotQ 年产能 12000 台人形产线
    "EVENT-0068": [["T3", 0.8]],  # 北京亦庄万台级超级工厂投用
    "EVENT-0135": [["T3.01", 1.0]],  # 智元突破万台量产
    "EVENT-0195": [["T3.01", 1.0]],  # 智元第 15000 台量产下线
    "EVENT-0417": [["T3.01", 0.8]],  # 鹿明 Prime R0 / 鹿小明 21DOF 全栈展示
    # 工业制造场景落地
    "EVENT-0095": [["T7.01", 0.7], ["T2.01", 0.5]],  # 精灵 G2 覆盖 3C 产线质检工段
    "EVENT-0198": [["T7.01", 0.8], ["T3.01", 0.6]],  # Galbot S1 宁德时代产线 7x24 常态化部署
    "EVENT-0354": [["T7.01", 0.8], ["T2.01", 0.6]],  # 钢板切割下料分拣产线 + 麻点缺陷检测
    # 低空与应急场景
    "EVENT-0357": [["T7.08", 1.0]],  # 县域全域低空智慧服务平台部署
    "EVENT-0358": [["T7.08", 1.0]],  # 低空综合治理无人机系统中标
    "EVENT-0360": [["T7.08", 0.7], ["T7.06", 0.6]],  # 应急巡检 800 公里 / 双光吊舱
    # 商业服务与物流仓储场景
    "EVENT-0416": [["T7.03", 0.9]],  # SenseMart OS 异构本体协同门店运营
    "EVENT-0421": [["T7.02", 0.9]],  # 四向穿梭车库 + WMS 十万台套级工厂
    # 端侧算力硬件
    "EVENT-0420": [["T3.08", 1.0]],  # 具身智能端侧 SoC 合资公司
}

SOURCE_CODE = "milestone_curated_lab"
SOURCE_NAME = "具身智能里程碑人工整理集"
# 二手摘要，不是采集原文，可靠度低于招聘源(85)和迁移工作簿(100)
DEFAULT_RELIABILITY = Decimal("60.00")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="把 embodied-job-evolution-lab 的技术里程碑导入本项目数据中枢。"
    )
    parser.add_argument("--sqlite", type=Path, required=True, help="旧实验库 app.db 路径")
    parser.add_argument(
        "--collected-at",
        type=date.fromisoformat,
        default=None,
        help="材料整理时间，默认取 sqlite 文件修改时间",
    )
    parser.add_argument(
        "--auto-verify",
        action="store_true",
        help="导入后直接置为 verified（新岗位发现只统计 verified 里程碑）",
    )
    parser.add_argument(
        "--verifier-code", default="admin-demo", help="--auto-verify 时记录的审核人 user_code"
    )
    parser.add_argument(
        "--estimate-missing-dates",
        action="store_true",
        help="文本里也抽不到日期时，按语料上界估算年份（只写年份，不编造具体日期）",
    )
    parser.add_argument(
        "--estimate-year",
        type=int,
        default=2026,
        help="--estimate-missing-dates 使用的年份，默认 2026（语料整理年份上界）",
    )
    parser.add_argument(
        "--link-curated-supplement",
        action="store_true",
        help="对无 technology_links 但描述含明确技术/场景的记录，套用人工补链接表",
    )
    parser.add_argument("--dry-run", action="store_true", help="只统计不写库")
    parser.add_argument("--limit", type=int, default=0, help="调试用，只处理前 N 条")
    return parser.parse_args()


YEAR_PATTERN = re.compile(r"(20[0-2]\d|19[6-9]\d)(?:[-/年](\d{1,2}))?(?:[-/月](\d{1,2}))?")


def parse_event_date(raw: str) -> tuple[date | None, int | None]:
    """旧库有 YYYY-MM-DD、纯年份和 '2023.0' 三种写法，只认能确定年份的。"""
    text = (raw or "").strip()
    if not text:
        return None, None
    try:
        return date.fromisoformat(text), date.fromisoformat(text).year
    except ValueError:
        pass
    head = text.split(".")[0].split("-")[0]
    if head.isdigit() and 1900 <= int(head) <= 2200:
        return None, int(head)
    return None, None


def recover_event_date(*texts: str) -> tuple[date | None, int | None]:
    """从来源标注、事件名称或描述里抽取真实日期，抽不到才算估算。"""
    for text in texts:
        match = YEAR_PATTERN.search(str(text or ""))
        if not match:
            continue
        year = int(match.group(1))
        if not 1900 <= year <= 2200:
            continue
        month, day = match.group(2), match.group(3)
        if month and day:
            try:
                return date(year, int(month), int(day)), year
            except ValueError:
                return None, year
        return None, year
    return None, None


def ensure_source(session, collected_at: datetime) -> DataSource:
    source = session.scalar(select(DataSource).where(DataSource.source_code == SOURCE_CODE))
    if source is not None:
        return source
    source = DataSource(
        source_code=SOURCE_CODE,
        source_name=SOURCE_NAME,
        source_type_code="curated",
        content_type_code="milestone",
        authority_level_code="secondary_summary",
        independent_source_group="curated_lab",
        default_reliability_score=DEFAULT_RELIABILITY,
        license_note=(
            "来自 embodied-job-evolution-lab 人工整理的里程碑摘要，"
            f"整理时间 {collected_at.date().isoformat()}；非采集原文，不含逐字网页正文。"
        ),
        source_status_code="active",
    )
    session.add(source)
    session.flush()
    return source


def build_content(name: str, description: str, source_text: str, event_id: str) -> tuple[str, str]:
    """返回 (正文, 引文)。引文必须是正文的逐字连续子串，服务层会校验。"""
    quote = (description or "").strip() or (name or "").strip()
    lines = [f"事件名称：{name.strip()}", f"事件描述：{quote}"]
    if (source_text or "").strip():
        lines.append(f"来源标注：{source_text.strip()}")
    lines.append(f"原始记录：embodied-job-evolution-lab/milestones/{event_id}")
    return "\n".join(lines), quote


def main() -> None:
    args = parse_args()
    if not args.sqlite.exists():
        raise SystemExit(f"找不到 sqlite 文件：{args.sqlite}")
    collected_at = (
        datetime.combine(args.collected_at, datetime.min.time())
        if args.collected_at
        else datetime.fromtimestamp(args.sqlite.stat().st_mtime)
    )

    db = sqlite3.connect(args.sqlite)
    rows = db.execute(
        "select event_id, name, description, event_date, source, event_type, technology_links"
        " from milestones order by event_id"
    ).fetchall()
    db.close()

    stats = {
        "总行数": len(rows),
        "无年份跳过": 0,
        "无技术链接跳过": 0,
        "技术编码失配跳过": 0,
        "缺名称跳过": 0,
        "人工补链接": 0,
        "日期从文本推出": 0,
        "日期估算为语料上界": 0,
        "导入": 0,
        "幂等命中": 0,
    }
    type_stats: dict[str, int] = {}

    with SessionLocal() as session:
        taxonomy = session.scalar(
            select(TechnologyTaxonomyVersion).where(
                TechnologyTaxonomyVersion.version_status_code == "active"
            )
        )
        if taxonomy is None:
            raise SystemExit("不存在已激活的技术词体系")
        active_codes = {
            code
            for (code,) in session.execute(
                select(TechnologyNode.technology_code).where(
                    TechnologyNode.taxonomy_version_id == taxonomy.taxonomy_version_id,
                    TechnologyNode.governance_status_code == "active",
                )
            )
        }
        ensure_source(session, collected_at)
        if not args.dry_run:
            session.commit()

        processed = 0
        imported_ids: list[int] = []
        for event_id, name, description, event_date_raw, source_text, event_type, links_raw in rows:
            if args.limit and processed >= args.limit:
                break
            if not (name or "").strip():
                stats["缺名称跳过"] += 1
                continue
            event_date, event_year = parse_event_date(event_date_raw)
            date_origin = "source_fact"
            if event_year is None:
                # 优先从来源标注/名称/描述里抽真实日期，抽不到才退到语料上界估算。
                event_date, event_year = recover_event_date(source_text, name, description)
                date_origin = "derived_date"
            if event_year is None:
                if not args.estimate_missing_dates:
                    stats["无年份跳过"] += 1
                    continue
                event_date, event_year = None, args.estimate_year
                date_origin = "estimated_date"
            if date_origin == "derived_date":
                stats["日期从文本推出"] += 1
            elif date_origin == "estimated_date":
                stats["日期估算为语料上界"] += 1
            try:
                links = json.loads(links_raw or "[]")
            except (TypeError, ValueError):
                links = []
            if not links and args.link_curated_supplement:
                links = CURATED_TECHNOLOGY_LINKS.get(event_id, [])
                if links:
                    stats["人工补链接"] += 1
            if not links:
                stats["无技术链接跳过"] += 1
                continue
            weights = {
                str(code): float(weight)
                for code, weight in links
                if str(code) in active_codes and float(weight) > 0
            }
            if not weights:
                stats["技术编码失配跳过"] += 1
                continue

            type_code = EVENT_TYPE_MAP.get((event_type or "").strip(), "other")
            type_stats[type_code] = type_stats.get(type_code, 0) + 1
            content_text, quote = build_content(name, description, source_text, event_id)
            if args.dry_run:
                stats["导入"] += 1
                processed += 1
                continue

            submission = MilestoneSubmission(
                data_source_code=SOURCE_CODE,
                source_record_key=event_id,
                canonical_url=f"curated://embodied-job-evolution-lab/milestone/{event_id}",
                title=name.strip()[:1000],
                content_text=content_text,
                published_at=None,
                collected_at=collected_at,
                milestone_name=name.strip()[:500],
                milestone_type_code=type_code,
                event_date=event_date,
                event_year=event_year,
                description_text=quote[:5000],
                maturity_delta_score=None,
                evidence_quote=quote,
                technology_codes=tuple(weights),
                extractor_code="curated-lab-milestone",
                extractor_version="1.0.0",
            )
            before = session.scalar(
                select(MilestoneEvent.milestone_event_id).where(
                    MilestoneEvent.milestone_name == name.strip()[:500]
                )
            )
            milestone = submit_milestone_candidate(session, submission)
            session.flush()
            if before is not None and before == milestone.milestone_event_id:
                stats["幂等命中"] += 1
            else:
                stats["导入"] += 1

            # 服务层把 relevance_score 固定写 100，这里按旧库的链接权重还原真实相关度。
            for relation in session.scalars(
                select(MilestoneTechnology).where(
                    MilestoneTechnology.milestone_event_id == milestone.milestone_event_id
                )
            ):
                node_code = session.scalar(
                    select(TechnologyNode.technology_code).where(
                        TechnologyNode.technology_node_id == relation.technology_node_id
                    )
                )
                if node_code in weights:
                    relation.relevance_score = Decimal(
                        str(round(min(1.0, weights[node_code]) * 100, 2))
                    )

            milestone.data_origin_code = date_origin
            imported_ids.append(milestone.milestone_event_id)
            processed += 1

        if args.auto_verify and not args.dry_run:
            stats["批量核实"] = _bulk_verify(session, imported_ids, args.verifier_code)
        if args.dry_run:
            session.rollback()
        else:
            session.commit()

    print(
        f"数据源：{SOURCE_CODE}（可靠度 {DEFAULT_RELIABILITY}，整理时间 {collected_at:%Y-%m-%d}）"
    )
    for key, value in stats.items():
        print(f"  {key}: {value}")
    print("  事件类型分布：")
    for code, count in sorted(type_stats.items(), key=lambda item: -item[1]):
        print(f"    {code}: {count}")


def _bulk_verify(session, milestone_ids: list[int], verifier_code: str) -> int:
    """走正规审核工作流核实，保证审核任务关闭并留下 ReviewAction 审计记录。"""
    from app.modules.data_center.models import AppUser, ReviewTask
    from app.modules.data_center.service import review_milestone

    user = session.scalar(select(AppUser).where(AppUser.user_code == verifier_code))
    if user is None:
        raise SystemExit(f"找不到审核人 {verifier_code}，无法执行 --auto-verify")
    verified = 0
    for milestone_id in milestone_ids:
        task = session.scalar(
            select(ReviewTask).where(
                ReviewTask.queue_code == "data_review",
                ReviewTask.target_type_code == "milestone",
                ReviewTask.target_id == milestone_id,
                ReviewTask.task_status_code.in_(["queued", "assigned", "reviewing"]),
            )
        )
        if task is None:
            continue
        review_milestone(
            session,
            task=task,
            actor_user_id=user.user_id,
            action_code="approve",
            comment_text="人工整理里程碑批量导入核实（curated_lab 数据源，二手摘要级证据）",
        )
        verified += 1
    return verified


if __name__ == "__main__":
    main()
