"""把审核后的英文别名草稿并入技术词变更集。

`propose_english_aliases.py` 产出的是**草稿**，本工具负责把它变成 v1.3 变更集的
`new_terms` 条目，之后仍走既有链路：`build_taxonomy_workbook.py` →
`stage_workbook` → `import_taxonomy`。词表的唯一权威来源始终是工作簿。

**三道拦截，任何一道不过就整体拒绝，不做部分导入。**

1. **跨技术点重复**——同一表面形式挂到多个技术点上，命中该归谁就取决于别名 id
   的顺序，是不确定行为。v1.2 治理已有同样的校验，这里沿用同一条规矩。
   实测草稿里有 8 条这类重复（如 dexterous manipulation 同时给了「具身操作」与
   「灵巧操作」），必须先在草稿里指定归属或删除其一。
2. **与既有别名冲突**——新别名撞上词表里已存在的表面形式，同理。
3. **高歧义别名未配上下文规则**——`needs_context_rule` 为真却没有
   `context_markers` 的一律拦下。英文技术词歧义比中文严重得多
   （transformer 是模型也是变压器，agent 是智能体也是代理人），裸放行会把大量
   无关文档误判成技术命中，而共现分析对假阳性尤其敏感。

**审核状态。** 只并入 `review_status == "approved"` 的条目。草稿默认全部为
`pending`，未经审核不会有任何东西进入变更集——这是刻意的，别名直接决定上游语料
的抽取结果，不能靠「默认通过」。

用法（backend 目录 / 容器内）：
    python -m tools.merge_english_aliases --draft /srv/data/governance/en_alias_draft.json \\
        --check-only
    python -m tools.merge_english_aliases --draft ... --out /srv/data/governance/v1_3.json
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from sqlalchemy import select

from app.db.session import SessionLocal
from app.modules.taxonomy.models import TechnologyAlias, TechnologyNode, TechnologyTaxonomyVersion

TERM_TYPE = "英文别名"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="把审核后的英文别名并入技术词变更集。")
    parser.add_argument("--draft", type=Path, required=True, help="propose_english_aliases 的产物")
    parser.add_argument("--out", type=Path, help="输出变更集路径")
    parser.add_argument("--base-version", default="v1.2")
    parser.add_argument("--target-version", default="v1.3")
    parser.add_argument("--effective-date", default="2026-08-26")
    parser.add_argument(
        "--check-only", action="store_true", help="只跑校验并报告，不生成变更集"
    )
    parser.add_argument(
        "--reject-ambiguous",
        action="store_true",
        help="把 needs_context_rule 的别名直接剔除，而不是要求为它们配上下文规则。"
        "**共现分析下这是更安全的默认**，理由见 triage_ambiguous 的说明",
    )
    parser.add_argument(
        "--drop-duplicates",
        action="store_true",
        help="把跨技术点重复的表面形式从**所有**技术点上剔除，而不是指定归属。"
        "保守做法：宁可漏掉也不要归错",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="跳过词表里已有的表面形式（通常只是大小写不同），而不是报错拦下",
    )
    parser.add_argument(
        "--accept-pending",
        action="store_true",
        help="把 review_status 仍为 pending 的条目也算作通过。"
        "**仅用于本机试跑**，正式升版必须逐条审核后置为 approved",
    )
    return parser.parse_args()


def existing_aliases() -> dict[str, str]:
    """词表里已有的表面形式 → 所属技术点名称。用于检测与既有别名冲突。"""
    with SessionLocal() as db:
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
        return {
            alias.alias_text.casefold(): nodes[alias.technology_node_id].technology_name
            for alias in db.scalars(select(TechnologyAlias))
            if alias.technology_node_id in nodes
        }


def triage_ambiguous(items: list[dict]) -> tuple[list[dict], list[str]]:
    """剔除高歧义别名。

    **为什么默认剔除而不是配上下文规则。** 这批别名服务的是共现分析，而共现分析对
    假阳性格外敏感：一个虚假命中会凭空造出一个「上游技术对」，而那恰恰是我们要检验
    的信号本身——用带噪的输入去验证一个关于共现的假设，结论无从解释。

    实测被标为高歧义的 65 条里，相当一部分即使配了上下文规则也不该要：
    `Deep Learning` 会匹配几乎所有 AI 论文，`visual perception` / `semantic memory` /
    `spatial representation` 是认知科学与心理学的固有术语，`SSL` 是
    Secure Sockets Layer，`task decomposition` 在运筹学与软件工程里通用。
    它们的问题不是「需要限定上下文」，而是**本身没有区分度**。

    剔除是保守选择：漏掉一个技术点的英文表述，代价是该技术在上游语料里被低估；
    收进一个泛化词，代价是它和一切东西都共现。前者可以靠人工补救，后者会污染结论。
    """
    kept, dropped = [], []
    for item in items:
        safe = [a for a in item["proposed"] if not a.get("needs_context_rule")]
        for alias in item["proposed"]:
            if alias.get("needs_context_rule"):
                dropped.append(
                    f"{alias['text']}（{item['technology_name']}）"
                    f"：{alias.get('ambiguity_note') or '存在其他常见义'}"
                )
        if safe:
            kept.append({**item, "proposed": safe})
    return kept, dropped


def drop_duplicate_surfaces(items: list[dict]) -> tuple[list[dict], list[str]]:
    """把跨技术点重复的表面形式从所有技术点上剔除。

    指定归属需要逐条判断语义（dexterous manipulation 该归「具身操作」还是
    「灵巧操作」），不是工具能替人做的决定。全删是保守选择——宁可漏掉也不要归错，
    归错会让该技术的共现统计整体偏移。被删的条目会列出来供人工补回。
    """
    owners: dict[str, set[str]] = defaultdict(set)
    for item in items:
        for alias in item["proposed"]:
            owners[alias["text"].casefold()].add(item["technology_code"])
    duplicated = {surface for surface, codes in owners.items() if len(codes) > 1}
    if not duplicated:
        return items, []
    kept, notes = [], []
    for item in items:
        safe = [a for a in item["proposed"] if a["text"].casefold() not in duplicated]
        for alias in item["proposed"]:
            if alias["text"].casefold() in duplicated:
                notes.append(f"{alias['text']}（{item['technology_name']}）")
        if safe:
            kept.append({**item, "proposed": safe})
    return kept, notes


def validate(items: list[dict], known: dict[str, str]) -> list[str]:
    errors: list[str] = []
    owners: dict[str, list[str]] = defaultdict(list)
    for item in items:
        for alias in item["proposed"]:
            owners[alias["text"].casefold()].append(item["technology_name"])

    for surface, holders in sorted(owners.items()):
        if len(holders) > 1:
            errors.append(
                f"跨技术点重复：「{surface}」同时挂到 {'、'.join(holders)}——"
                "命中归属会取决于别名 id 顺序，必须指定归属或删除其一"
            )
        if surface in known:
            errors.append(
                f"与既有别名冲突：「{surface}」在词表中已属于「{known[surface]}」"
            )

    for item in items:
        for alias in item["proposed"]:
            if alias.get("needs_context_rule") and not alias.get("context_markers"):
                errors.append(
                    f"高歧义别名未配上下文规则：「{alias['text']}」"
                    f"（{item['technology_name']}）——"
                    f"{alias.get('ambiguity_note') or '存在其他常见义'}"
                )
    return errors


def main() -> None:
    args = parse_args()
    draft = json.loads(args.draft.read_text(encoding="utf-8"))
    accepted = "approved" if not args.accept_pending else None
    items = [
        item
        for item in draft["items"]
        if accepted is None or item.get("review_status") == accepted
    ]
    if args.accept_pending:
        items = [item for item in draft["items"] if item.get("review_status") != "rejected"]

    print(f"草稿共 {len(draft['items'])} 个技术点，本次纳入 {len(items)} 个")
    if not items:
        raise SystemExit(
            "没有条目通过审核。草稿默认全部为 pending——别名直接决定上游语料的抽取结果，"
            "不设「默认通过」。逐条审核后把 review_status 置为 approved 再运行。"
        )

    if args.reject_ambiguous:
        items, dropped = triage_ambiguous(items)
        print(f"\n剔除高歧义别名 {len(dropped)} 条（共现分析下假阳性比假阴性更糟）：")
        for line in dropped[:12]:
            print(f"  - {line}")
        if len(dropped) > 12:
            print(f"  …另有 {len(dropped) - 12} 条，全部记入变更集的 rejected_ambiguous")
        rejected_ambiguous = dropped
    else:
        rejected_ambiguous = []

    if args.drop_duplicates:
        items, dupes = drop_duplicate_surfaces(items)
        if dupes:
            print(f"\n剔除跨技术点重复的表面形式 {len(dupes)} 条（归属需人工判断）：")
            for line in dupes:
                print(f"  - {line}")
        rejected_duplicates = dupes
    else:
        rejected_duplicates = []

    known = existing_aliases()
    if args.skip_existing:
        # 词表里已有同一表面形式（往往只是大小写差异），说明这个词本来就能匹配，
        # 重复登记没有意义，跳过即可，不构成升版的阻塞。
        skipped = []
        trimmed = []
        for item in items:
            safe = [a for a in item["proposed"] if a["text"].casefold() not in known]
            for alias in item["proposed"]:
                if alias["text"].casefold() in known:
                    skipped.append(f"{alias['text']} → 已属于「{known[alias['text'].casefold()]}」")
            if safe:
                trimmed.append({**item, "proposed": safe})
        items = trimmed
        if skipped:
            print(f"\n跳过词表中已存在的表面形式 {len(skipped)} 条：")
            for line in skipped[:10]:
                print(f"  - {line}")

    errors = validate(items, known)
    stats = Counter()
    for item in items:
        stats["技术点"] += 1
        stats["别名"] += len(item["proposed"])
        stats["需上下文规则"] += sum(1 for a in item["proposed"] if a.get("needs_context_rule"))
    print(json.dumps(dict(stats), ensure_ascii=False, indent=2))

    if errors:
        print(f"\n校验未通过，共 {len(errors)} 条：")
        for line in errors[:40]:
            print(f"  - {line}")
        if len(errors) > 40:
            print(f"  …另有 {len(errors) - 40} 条")
        raise SystemExit("\n任何一条未解决都不生成变更集——不做部分导入。")

    print("\n校验通过。")
    if args.check_only or not args.out:
        return

    new_terms = [
        {
            "term": alias["text"],
            "l3_code": item["technology_code"],
            "type": TERM_TYPE,
            "reason": (
                f"英文语料抽取所需；{item['technology_name']} 此前无可匹配的英文表面形式"
            ),
            **(
                {"context_markers": alias["context_markers"]}
                if alias.get("context_markers")
                else {}
            ),
        }
        for item in items
        for alias in item["proposed"]
    ]
    changeset = {
        "base_version": args.base_version,
        "target_version": args.target_version,
        "effective_date": args.effective_date,
        "change_summary": (
            f"为 {stats['技术点']} 个 L3 技术点补充 {stats['别名']} 条英文别名，"
            "使上游英文语料（arXiv 论文）可被抽取。补充前英文覆盖率仅 17%"
            "（242 个 L3 中 40 个有纯英文别名），识别不到的技术在共现分析中会"
            "看起来永远不共现，结论会被系统性扭曲。"
        ),
        # provenance 的三个键与 build_taxonomy_workbook 的「来源明细(留痕)」列对应，
        # 缺一个就会在渲染工作簿时报 KeyError。
        "provenance": {
            "retire_terms": "本次不下线任何词",
            "new_l3": "本次不新增 L3",
            "new_terms": (
                "tools/propose_english_aliases.py 生成、"
                f"{draft.get('prompt_version')} 提示词；"
                "高歧义词与跨技术点重复词已剔除，详见 rejected_* 字段"
            ),
            "generated_by": "tools/propose_english_aliases.py",
            "prompt_version": draft.get("prompt_version"),
            "reviewed": not args.accept_pending,
        },
        "retire_terms": [],
        "new_l3": [],
        "new_terms": new_terms,
        # 被剔除的条目一并留档：它们不是「没生成出来」，是**判断后不要的**，
        # 后续若要补回需要有据可查。
        "rejected_ambiguous": rejected_ambiguous,
        "rejected_duplicates": rejected_duplicates,
    }
    args.out.write_text(json.dumps(changeset, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"变更集已写入 {args.out}（{len(new_terms)} 条 new_terms）")


if __name__ == "__main__":
    main()
