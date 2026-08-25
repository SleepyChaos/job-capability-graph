"""为 L3 技术点批量生成英文别名候选，产出**待人工审核**的变更集草稿。

**为什么需要。** 上游语料（arXiv 论文、专利）是英文的，而现有词表是中文导向的：
2,039 条可匹配别名里纯英文只有 147 条，242 个 L3 技术点中只有 40 个有纯英文别名，
覆盖率 17%。直接拿它去抽英文语料，识别不到的技术会**看起来永远不共现**——
共现分析会被这个缺口系统性扭曲，结论方向都可能是反的。见《16》任务书 U-1。

**这个工具只生成草稿，不落库。** 产出的 JSON 需要人工逐条审核后，才并入
`taxonomy_v1_x_changeset.json` 的 `new_terms`，再走既有的
`build_taxonomy_workbook.py` → `stage_workbook` → `import_taxonomy` 链路。
词表的唯一权威来源仍是工作簿，这条规矩不因为新增了英文别名而改变。

**高歧义别名单独标出。** 英文技术词的歧义比中文严重得多——`transformer` 是模型
还是变压器，`attention` 是机制还是普通词义，`agent` 是智能体还是代理人。模型被
要求为这类词标注 `needs_context_rule`，人工审核时必须为它们配上下文标记词，
否则不得放行；裸放行会把大量无关文档误判成技术命中。

用法（backend 目录 / 容器内）：
    python -m tools.propose_english_aliases --out /srv/data/governance/en_alias_draft.json
    python -m tools.propose_english_aliases --domains T1,T2 --limit 20 --dry-run
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.infrastructure.llm import generate, llm_available
from app.modules.taxonomy.models import TechnologyAlias, TechnologyNode, TechnologyTaxonomyVersion

PROMPT_VERSION = "english_alias_proposal_v2_specificity_guarded"
# 一次问几个技术点。太多会让模型偷懒（后几个明显敷衍），太少浪费往返。
BATCH_SIZE = 6


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="为 L3 技术点生成英文别名候选。")
    parser.add_argument("--out", type=Path, help="草稿输出路径；省略则打印到标准输出")
    parser.add_argument("--domains", default="", help="限定 L1 域，逗号分隔，如 T1,T2,T3,T4")
    parser.add_argument("--limit", type=int, default=0, help="最多处理多少个技术点，0 为不限")
    parser.add_argument(
        "--only-uncovered",
        action="store_true",
        help="只处理完全没有纯英文别名的技术点。"
        "**默认是全部处理**——「已有英文别名」不等于「已有可用的英文全称」："
        "强化学习已有 PPO/DQN/SAC/TD3，运动规划已有 MoveIt，模仿学习已有 "
        "Diffusion Policy，全是缩写与产品名，恰恰缺 reinforcement learning / "
        "motion planning / imitation learning 这些正文里最常出现的全称。"
        "首轮用「只补没有的」作默认，直接漏掉了这批最基本的词。",
    )
    parser.add_argument("--dry-run", action="store_true", help="只列出待处理的技术点，不调用 LLM")
    return parser.parse_args()


def is_pure_english(text: str) -> bool:
    return not re.search(r"[一-鿿]", text) and bool(re.search(r"[A-Za-z]", text))


def load_targets(db: Session, args: argparse.Namespace) -> list[dict]:
    """取需要补英文别名的 L3 技术点，附带它们现有的中文别名作为语义线索。"""
    version_id = db.scalar(
        select(TechnologyTaxonomyVersion.taxonomy_version_id)
        .where(TechnologyTaxonomyVersion.version_status_code == "active")
        .order_by(TechnologyTaxonomyVersion.effective_date.desc())
        .limit(1)
    )
    nodes = {
        node.technology_node_id: node
        for node in db.scalars(
            select(TechnologyNode).where(TechnologyNode.taxonomy_version_id == version_id)
        )
    }

    def l3_ancestor(node_id: int) -> TechnologyNode | None:
        node, seen = nodes.get(node_id), set()
        while node and node.technology_node_id not in seen:
            if node.level_code == "L3":
                return node
            seen.add(node.technology_node_id)
            node = nodes.get(node.parent_technology_node_id)
        return None

    aliases_by_l3: dict[str, list[str]] = {}
    english_l3: set[str] = set()
    for alias in db.scalars(select(TechnologyAlias).where(TechnologyAlias.is_matchable.is_(True))):
        owner = l3_ancestor(alias.technology_node_id)
        if owner is None:
            continue
        aliases_by_l3.setdefault(owner.technology_code, []).append(alias.alias_text)
        if is_pure_english(alias.alias_text):
            english_l3.add(owner.technology_code)

    domains = {item.strip() for item in args.domains.split(",") if item.strip()}
    targets = []
    for node in nodes.values():
        if node.level_code != "L3" or node.governance_status_code != "active":
            continue
        if domains and node.technology_code.split(".")[0] not in domains:
            continue
        if args.only_uncovered and node.technology_code in english_l3:
            continue
        parent = nodes.get(node.parent_technology_node_id)
        targets.append({
            "technology_code": node.technology_code,
            "technology_name": node.technology_name,
            "parent_name": parent.technology_name if parent else None,
            "existing_aliases": sorted(aliases_by_l3.get(node.technology_code, []))[:12],
        })
    targets.sort(key=lambda item: item["technology_code"])
    return targets[: args.limit] if args.limit else targets


SYSTEM_PROMPT = (
    "你是技术词表治理助手，为中文技术点补充**英文别名**，供英文论文与专利语料的"
    "字符串匹配使用。\n"
    "硬约束：\n"
    "1. 只产出该技术点在英文文献中**真实使用**的表述，包括全称、常用缩写与常见变体。"
    "不要直译中文名，不要造词。\n"
    "2. 别名必须能在正文中直接字符串匹配，因此不要带修饰语、不要写成句子。\n"
    "3. **不确定就少给**，每个技术点 2–4 个即可。宁可只给两个可靠别名也不要凑数——"
    "错误别名会把无关文档误判成技术命中，比漏掉更糟。\n"
    "4. 别名必须**特指该技术**，不得是以下三类：\n"
    "   (a) 所属大类的通称（如给「大模型部署与推理优化」写 large model deployment）；\n"
    "   (b) 其他学科的固有术语（如给「大小脑分层架构」写 cerebro-cerebellar loop，"
    "那会匹配到真正的神经科学论文）；\n"
    "   (c) 具体产品或论文的专名（如 Galaxea G0.5、NeuroVLA），它们几乎不会在"
    "他人文献中出现，给了也是空转。\n"
    "5. 逐条标注 `needs_context_rule`：该词在英文里若存在与本技术无关的常见义"
    "（如 transformer 既是模型也是变压器，agent 既是智能体也是代理人，"
    "attention 既是机制也是普通词义），标 true，并在 `ambiguity_note` 写明另一种含义。\n"
    "6. 缩写只在业内确实通用时给出，并且长度不少于 2 个字符。\n"
    "输出 JSON：{\"items\": [{\"technology_code\": ..., \"aliases\": "
    "[{\"text\": ..., \"needs_context_rule\": bool, \"ambiguity_note\": ...}]}]}"
)


def propose(batch: list[dict]) -> list[dict]:
    payload = {
        "technologies": [
            {
                "technology_code": item["technology_code"],
                "chinese_name": item["technology_name"],
                "parent": item["parent_name"],
                "known_aliases": item["existing_aliases"],
            }
            for item in batch
        ]
    }
    result = generate(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=json.dumps(payload, ensure_ascii=False),
        prompt_version=PROMPT_VERSION,
        json_mode=True,
    )
    if result is None or not isinstance(result.parsed_json, dict):
        return []
    items = result.parsed_json.get("items")
    return items if isinstance(items, list) else []


def main() -> None:
    args = parse_args()
    with SessionLocal() as session:
        targets = load_targets(session, args)

    print(f"待补英文别名的 L3 技术点：{len(targets)}")
    if args.dry_run:
        for item in targets[:30]:
            print(f"  {item['technology_code']}  {item['technology_name']}")
        return
    if not llm_available():
        raise SystemExit("LLM 网关无 API Key，无法生成别名候选")

    by_code = {item["technology_code"]: item for item in targets}
    proposals: list[dict] = []
    stats: Counter[str] = Counter()
    for start in range(0, len(targets), BATCH_SIZE):
        batch = targets[start : start + BATCH_SIZE]
        for item in propose(batch):
            code = item.get("technology_code")
            source = by_code.get(code)
            if source is None:
                stats["技术编码不匹配丢弃"] += 1
                continue
            kept = []
            for alias in item.get("aliases") or []:
                text = str(alias.get("text", "")).strip()
                # 生成侧再兜一道：非英文、过短的一律丢弃，不指望提示词百分百被遵守。
                if not text or not is_pure_english(text) or len(text) < 2:
                    stats["非英文或过短丢弃"] += 1
                    continue
                kept.append({
                    "text": text,
                    "needs_context_rule": bool(alias.get("needs_context_rule")),
                    "ambiguity_note": (alias.get("ambiguity_note") or "").strip() or None,
                })
            if not kept:
                continue
            stats["技术点"] += 1
            stats["别名"] += len(kept)
            stats["需配上下文规则"] += sum(1 for a in kept if a["needs_context_rule"])
            proposals.append({
                "technology_code": code,
                "technology_name": source["technology_name"],
                "existing_aliases": source["existing_aliases"],
                "proposed": kept,
                # 人工审核后改成 approved / rejected，只有 approved 的才并入变更集。
                "review_status": "pending",
                "review_notes": None,
            })
        print(f"  已处理 {min(start + BATCH_SIZE, len(targets))}/{len(targets)}")

    draft = {
        "prompt_version": PROMPT_VERSION,
        "note": (
            "本文件是待人工审核的草稿，不可直接导入。审核通过的条目需并入技术词变更集的 "
            "new_terms，再走 build_taxonomy_workbook → stage_workbook → import_taxonomy。"
            "needs_context_rule 为 true 的别名必须先配上下文标记词，不得裸放行。"
        ),
        "stats": dict(stats),
        "items": proposals,
    }
    text = json.dumps(draft, ensure_ascii=False, indent=1)
    if args.out:
        args.out.write_text(text, encoding="utf-8")
        print(f"\n草稿已写入 {args.out}")
    else:
        print(text)
    print(json.dumps(dict(stats), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
