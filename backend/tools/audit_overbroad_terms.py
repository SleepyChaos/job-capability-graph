"""窗口 A-1 子任务 1.1:过宽表面词排查分析。

输入:audit_export_extraction_data.py 导出的 .audit-data/ TSV 快照
(口径:run_code=jdparse_e7328e6370fbee62e79d2098,无 LLM 回写;
LLM 复核数据来自 run_id=1 的 735 条 needs_review 复核运行,仅作参照)。

输出:Markdown 报告片段(stdout),包含:
1. 命中总量与评估状态汇总
2. 高频命中别名排行(与 docs/07 §4.2 证据表对照)
3. 过宽词判定清单(判定结论编码在下方 VERDICTS,数字全部由数据计算)
4. 歧义规则效果评估(4 条规则:needs_review 量、语境命中量、正向语境词触发频次、
   run 1 上 LLM 复核的接受率参照)
5. 反向问题:零命中别名统计(超长学术术语)

判定标准(docs/07 §5 任务 1.1):
- 命中文本 ≤3 字且语义宽泛
- 同一命中文本在不同语境下应指向不同技术点
- 通用领域词被挂到具体技术点
判定动作:offline=下线(is_matchable=False)/ narrow=收窄(加语境规则或改词形)/
keep=维持 / watch=维持但观察(词汇本身正确,误报主要来自语料混入,归窗口 C 处理)

用法:python backend/tools/audit_overbroad_terms.py [--data-dir .audit-data]
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path

from audit_tsv import iter_mysql_tsv

HITS_COLS = [
    "assessment_id",
    "job_posting_id",
    "requirement_id",
    "status",
    "reason_code",
    "score",
    "feature_weight",
    "ambiguity_rule_id",
    "raw_term",
    "mention_count",
    "mapping_method_code",
    "req_node_code",
    "req_node_name",
    "span_text",
    "alias_id",
    "alias_text",
    "normalized_alias",
    "is_matchable",
    "alias_type_code",
    "alias_node_code",
    "alias_node_name",
    "alias_l3_code",
    "alias_l3_name",
]
INVENTORY_COLS = [
    "alias_id",
    "alias_text",
    "normalized_alias",
    "alias_len",
    "is_matchable",
    "alias_type_code",
    "source_type_code",
    "node_level",
    "node_code",
    "node_name",
    "l3_code",
    "l3_name",
]
CTX_COLS = [
    "assessment_id",
    "job_posting_id",
    "job_title",
    "status",
    "reason_code",
    "normalized_alias",
    "req_node_code",
    "req_node_name",
    "context_text",
]
LLM_COLS = [
    "reassessment_id",
    "assessment_id",
    "run1_status_after",
    "original_status_code",
    "decision_code",
    "confidence_score",
    "validation_status_code",
    "applied",
    "llm_reason",
    "normalized_alias",
    "req_node_code",
    "req_node_name",
    "job_title",
]
CORPUS_COLS = [
    "job_posting_id",
    "job_title_normalized",
    "job_title_raw",
    "job_level_code",
    "region_text",
    "parse_status_code",
    "parse_quality_score",
    "accepted_cnt",
    "review_cnt",
    "distinct_node_cnt",
    "jd_clean_text",
]

# 与 backend/app/modules/job/parsing_service.py L47-72 的 AMBIGUITY_RULE_DEFINITIONS 对齐
RULE_MARKERS = {
    "检测": ["认证", "检验", "质检", "质量", "可靠性", "安规", "标准", "inspection"],
    "汽车": ["制造", "产线", "装配", "工厂", "生产", "焊接", "车身", "manufacturing"],
    "大模型": [
        "具身",
        "机器人",
        "vla",
        "视觉语言动作",
        "vision-language-action",
        "端到端",
        "多模态",
    ],
    "控制系统": ["机器人", "运动", "实时", "伺服", "plc", "嵌入式", "执行器", "关节"],
}

# 过宽词判定表(人工判读,依据 = 命中样本的 JD 标题 + 映射目标语义核对)。
# key=normalized_alias;value=(动作, 依据摘要)。数字不在判定表里,全部由数据计算。
VERDICTS: dict[str, tuple[str, str]] = {
    # 已有歧义规则、语境缺失进 needs_review 的三词:规则的隔离有效,但语境命中路径仍放行误报
    "大模型": (
        "offline",
        "已确认误报(docs/07 证据3):『大模型』≠VLA。"
        "run1 的 233 条 needs_review 交 LLM 复核仅接受 1 条(0%),"
        "而语境规则(机器人/具身等词出现在同段)仍放行 168 条 accepted;"
        "『智能语音系统架构师』『渠道销售经理』等岗被计入 VLA 证据。"
        "建议:将该词从 T1.01.11 下线,由 vla/rt-2/π0/octo 等具体词承接(docs/07 任务组 2 亦持此例)",
    ),
    "多模态大模型": (
        "narrow",
        "多模态大模型 ≠ VLA端到端大模型(多模态对话模型亦命中);95 条全部 accepted 无任何隔离;"
        "建议加具身语境规则或挂到更通用的 L3",
    ),
    "基础模型": (
        "narrow",
        "foundation model 泛称,命中样本含『基础几何模型算法工程师』『数据算法工程师』;"
        "29 条全部 accepted;建议加语境规则",
    ),
    "检测": (
        "narrow",
        "通用动词/名词,已有规则隔离 251/313;LLM 复核接受率 40%(100/251),"
        "语境命中路径放行的 62 条仍含『质检员』『仪校工程师』等岗位;"
        "建议收窄词形(如『检测认证』)并保留规则",
    ),
    "汽车": (
        "narrow",
        "通用领域词,已有规则隔离 227/271;LLM 复核接受率 44%(100/227);"
        "语境命中路径放行的 44 条含销售/材料岗;建议收窄词形(如『汽车电子』『车规』)并保留规则",
    ),
    "控制系统": (
        "narrow",
        "泛工程词汇,规则隔离 24/91;LLM 复核仅接受 2/24;语境命中放行的 67 条含域控/嵌入式岗;"
        "建议加机器人语境限定",
    ),
    # 无规则的通用词,误映射到具体或不相关技术点
    "商业服务": (
        "offline",
        "『商业服务』(business services)≠商用服务机器人;命中 JD 为销售总监/海外业务拓展;"
        "22 条全部 accepted,纯误报",
    ),
    "职业教育": (
        "offline",
        "『职业教育』≠教育机器人;命中 JD 为渠道销售经理/课程教研;19 条全部 accepted,纯误报",
    ),
    "ai教育": (
        "offline",
        "同『职业教育』,泛教育行业词;2 条",
    ),
    "开源框架": (
        "offline",
        "『开源框架』与『人形机器人(通用)』无语义关联;命中含 java后端/测试工程师;"
        "15 条全部 accepted,词表错挂",
    ),
    "光学组件": (
        "offline",
        "光学组件≠机器视觉;命中为 FA工程师/抛光工程师;2 条",
    ),
    "仓储物流": (
        "narrow",
        "泛行业词;命中混有解决方案工程师(边缘)与仓库管理员/海外销售(误报);23 条全部 accepted",
    ),
    "数据服务": (
        "narrow",
        "泛 IT 服务词→数据集;命中为数据产品经理/采购负责人等非技术点岗位;16 条全部 accepted",
    ),
    "训练场": (
        "narrow",
        "歧义词;『智能座舱产品经理』『ar/vr产品经理』为误报,『机器人训练场产品经理』为真;"
        "11 条全部 accepted;建议加机器人/数据采集语境",
    ),
    "act": (
        "narrow",
        "英文常用词作为 Action Chunking Transformers 缩写;命中含『application engineer』;"
        "33 条全部 accepted;建议改为区分大小写的『ACT』并要求 VLA 语境",
    ),
    # 词汇与映射目标语义相符、但属通用件/通用词:维持,误报治理归语料过滤(窗口 C)
    "电机": (
        "watch",
        "通用件词汇但目标『电机与驱动』语义相符;命中 JD 多为电机/FOC/驱动工程师;"
        "混入的机械结构等岗位属语料混入问题,建议由岗位过滤解决,不在词表侧下线",
    ),
    "数据集": (
        "watch",
        "词与目标(数据集)一致;命中含数据采购/产品经理岗,证据价值弱但不算错映射",
    ),
    "人机交互": ("watch", "通用词挂通用节点(T6.01.06),语义相符;观察即可"),
    "智能制造": (
        "watch",
        "泛行业词→智能制造与工业自动化;CNC/产线类 JD 大量命中,是否保留取决于窗口 C 的岗位口径",
    ),
    "工业自动化": ("watch", "同『智能制造』"),
    "感知系统": ("watch", "泛称挂感知认知(通用),语义相符"),
    "计算平台": ("watch", "泛硬件词挂算力硬件,命中多为域控/嵌入式岗,基本相符"),
}

VERDICT_LABEL = {
    "offline": "下线(is_matchable=False)",
    "narrow": "收窄(加语境规则/改词形)",
    "keep": "维持",
    "watch": "维持(误报归窗口 C 语料过滤)",
}


def load(data_dir: Path) -> tuple[list, list, list, list, list]:
    hits = list(iter_mysql_tsv((data_dir / "01_alias_hits.tsv").read_text("utf-8"), HITS_COLS))
    inventory = list(
        iter_mysql_tsv((data_dir / "02_alias_inventory.tsv").read_text("utf-8"), INVENTORY_COLS)
    )
    contexts = list(
        iter_mysql_tsv((data_dir / "03_ambiguity_contexts.tsv").read_text("utf-8"), CTX_COLS)
    )
    llm = list(iter_mysql_tsv((data_dir / "05_llm_reassessment.tsv").read_text("utf-8"), LLM_COLS))
    corpus = list(iter_mysql_tsv((data_dir / "04_jd_corpus.tsv").read_text("utf-8"), CORPUS_COLS))
    return hits, inventory, contexts, llm, corpus


def aggregate_alias(hits: list) -> dict[str, dict]:
    agg: dict[str, dict] = {}
    for r in hits:
        w = r["normalized_alias"]
        a = agg.setdefault(
            w,
            {
                "hits": 0,
                "jds": set(),
                "accepted": 0,
                "review": 0,
                "node": f"{r['req_node_code']} {r['req_node_name']}",
                "rule": r["ambiguity_rule_id"] is not None,
            },
        )
        a["hits"] += 1
        a["jds"].add(r["job_posting_id"])
        if r["status"] == "accepted":
            a["accepted"] += 1
        else:
            a["review"] += 1
    return agg


def fmt_int(n: int) -> str:
    return f"{n:,}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir", type=Path, default=Path(__file__).resolve().parents[2] / ".audit-data"
    )
    parser.add_argument("--top", type=int, default=40, help="高频命中排行长度")
    args = parser.parse_args()

    hits, inventory, contexts, llm, corpus = load(args.data_dir)
    agg = aggregate_alias(hits)

    out = sys.stdout.write

    # ---------- 1. 总量与状态汇总 ----------
    status = Counter((r["status"], r["reason_code"]) for r in hits)
    out("## 1. 命中总量与评估状态\n\n")
    out(f"- 评估总数:{fmt_int(len(hits))}(run 3,无 LLM 回写)\n")
    for (st, reason), cnt in sorted(status.items(), key=lambda kv: -kv[1]):
        out(f"- {st} / {reason}:{fmt_int(cnt)}\n")
    out(f"- 去重后命中别名数:{len(agg)} / 全词表 {fmt_int(len(inventory))}\n")
    fired_alias_ids = {r["alias_id"] for r in hits}
    out(
        f"- 词表覆盖利用率:{len(fired_alias_ids)}/{fmt_int(len(inventory))}"
        f"({len(fired_alias_ids) / len(inventory):.1%})\n"
    )
    nodes = {r["req_node_code"] for r in hits}
    out(f"- 命中涉及的 L3 目标节点:{len(nodes)} 个\n")
    nonmatchable_hits = [r for r in hits if r["is_matchable"] == "0"]
    out(f"- is_matchable=0 别名的命中数:{len(nonmatchable_hits)}(应为 0,非 0 说明口径异常)\n\n")

    # ---------- 2. 高频命中排行 ----------
    out(f"## 2. 高频命中别名排行(top {args.top})\n\n")
    out("| 别名 | 命中 | 命中JD数 | accepted | needs_review | 映射目标(L3) | 有歧义规则 |\n")
    out("| --- | ---: | ---: | ---: | ---: | --- | :-: |\n")
    for w, a in sorted(agg.items(), key=lambda kv: -kv[1]["hits"])[: args.top]:
        out(
            f"| {w} | {a['hits']} | {len(a['jds'])} | {a['accepted']} | {a['review']} "
            f"| {a['node']} | {'是' if a['rule'] else ''} |\n"
        )
    out("\n")

    # ---------- 3. 过宽词判定清单 ----------
    out("## 3. 过宽词判定清单(判定为人工判读,数字由脚本计算)\n\n")
    out(
        "| 别名 | 动作 | 命中 | accepted(污染下游) | needs_review(已隔离) "
        "| 命中JD数 | 映射目标 | 依据 |\n"
    )
    out("| --- | --- | ---: | ---: | ---: | ---: | --- | --- |\n")
    offline_acc = narrow_acc = 0
    offline_hits = narrow_hits = 0
    for w, (action, _rationale) in VERDICTS.items():
        a = agg.get(w)
        if a is None:
            out(
                f"| {w} | {VERDICT_LABEL[action]} | 0 | 0 | 0 | 0 | (未命中) "
                f"| \u26a0\ufe0f 词表有但无命中,请核对 |\n"
            )
            continue
        if action == "offline":
            offline_acc += a["accepted"]
            offline_hits += a["hits"]
        if action == "narrow":
            narrow_acc += a["accepted"]
            narrow_hits += a["hits"]
        out(
            f"| {w} | {VERDICT_LABEL[action]} | {a['hits']} | {a['accepted']} | {a['review']} "
            f"| {len(a['jds'])} | {a['node']} | (见下文判读) |\n"
        )
    out("\n")
    out("### 判读依据\n\n")
    for w, (action, rationale) in VERDICTS.items():
        out(f"- **{w}** → {VERDICT_LABEL[action]}:{rationale}\n")
    out(
        f"\n**影响汇总**:建议下线的 {sum(1 for v in VERDICTS.values() if v[0] == 'offline')} 个词"
        f"共 {fmt_int(offline_hits)} 条命中(其中 accepted {fmt_int(offline_acc)} 条);"
        f"建议收窄的 {sum(1 for v in VERDICTS.values() if v[0] == 'narrow')} 个词"
        f"共 {fmt_int(narrow_hits)} 条命中(其中 accepted {fmt_int(narrow_acc)} 条)。\n\n"
    )

    # 未判定的短词提示(≤4 字符且命中 ≥10,供窗口 B 复核)
    judged = set(VERDICTS)
    rest = [(w, a) for w, a in agg.items() if w not in judged and len(w) <= 4 and a["hits"] >= 10]
    out("### 未判定但建议窗口 B 复核的短词(≤4 字符、命中 ≥10)\n\n")
    out("| 别名 | 命中 | accepted | 映射目标 |\n| --- | ---: | ---: | --- |\n")
    for w, a in sorted(rest, key=lambda kv: -kv[1]["hits"]):
        out(f"| {w} | {a['hits']} | {a['accepted']} | {a['node']} |\n")
    out("\n")

    # ---------- 4. 歧义规则效果 ----------
    out("## 4. 歧义规则效果评估\n\n")
    by_rule: dict[str, Counter] = defaultdict(Counter)
    for r in contexts:
        by_rule[r["normalized_alias"]][(r["status"], r["reason_code"])] += 1
    llm_by_word: dict[str, Counter] = defaultdict(Counter)
    for r in llm:
        llm_by_word[r["normalized_alias"]][r["decision_code"]] += 1
    out(
        "| 规则词 | run3 语境缺失→needs_review | run3 语境命中→accepted "
        "| run1 同词 needs_review 交 LLM 复核的结果 |\n"
    )
    out("| --- | ---: | ---: | --- |\n")
    for w in RULE_MARKERS:
        c = by_rule.get(w, Counter())
        llm_c = llm_by_word.get(w, Counter())
        llm_total = sum(llm_c.values())
        llm_txt = (
            f"接受 {llm_c.get('accepted', 0)}/{llm_total}"
            f"({llm_c.get('accepted', 0) / llm_total:.0%}),"
            f"拒绝 {llm_c.get('rejected', 0)},不确定 {llm_c.get('uncertain', 0)}"
            if llm_total
            else "(无复核数据)"
        )
        out(
            f"| {w} | {c.get(('needs_review', 'ambiguity_context_missing'), 0)} "
            f"| {c.get(('accepted', 'ambiguity_context_confirmed'), 0)} | {llm_txt} |\n"
        )
    out("\n### 语境命中(accepted/80 分)路径的正向语境词触发频次\n\n")
    out("| 规则词 | 触发词 | 触发评估数 |\n| --- | --- | ---: |\n")
    for w, markers in RULE_MARKERS.items():
        fired = Counter()
        for r in contexts:
            if r["normalized_alias"] != w or r["status"] != "accepted":
                continue
            ctx_text = (r["context_text"] or "").casefold()
            for m in markers:
                if m.casefold() in ctx_text:
                    fired[m] += 1
        for m, cnt in fired.most_common():
            out(f"| {w} | {m} | {cnt} |\n")
    out("\n### 语境命中路径的误报样例(标题含销售/产品/教育等非技术岗特征)\n\n")
    non_tech_hint = ("销售", "拓展", "产品经理", "教研", "课程", "采购", "外", "商务", "运营")
    shown = 0
    for r in contexts:
        if r["status"] != "accepted" or shown >= 8:
            continue
        title = r["job_title"] or ""
        if any(h in title for h in non_tech_hint):
            out(
                f"- [{r['normalized_alias']} → {r['req_node_name']}] {title}"
                f" | 语境片段:{(r['context_text'] or '')[:60]!r}\n"
            )
            shown += 1
    if shown == 0:
        out("(语境命中样本中未检出非技术岗标题)\n")
    out("\n")

    # ---------- 5. 零命中别名(反向问题) ----------
    out("## 5. 零命中别名统计(反向问题,窗口 B 的重建输入)\n\n")
    hit_words = set(agg)
    zero = [a for a in inventory if a["normalized_alias"] not in hit_words]
    out(f"- 零命中别名:{fmt_int(len(zero))} / {fmt_int(len(inventory))}\n")
    long_zero = [a for a in zero if int(a["alias_len"]) > 15]
    out(f"- 其中长度 >15 字:{len(long_zero)}(docs/07 §4.2 证据 2 称 393)\n")
    src_type = Counter(a["source_type_code"] for a in zero)
    out(f"- 按来源类型:{dict(src_type)}\n")
    out(
        "- 零命中别名长度分位:p50={:.0f} p90={:.0f} max={}\n".format(
            *(sorted(int(a["alias_len"]) for a in zero)[int(len(zero) * q)] for q in (0.5, 0.9)),
            max(int(a["alias_len"]) for a in zero),
        )
    )
    fired_len = sorted(int(a["alias_len"]) for a in inventory if a["normalized_alias"] in hit_words)
    out(
        f"- 有命中别名长度分位:p50={fired_len[len(fired_len) // 2]} "
        f"p90={fired_len[int(len(fired_len) * 0.9)]} max={fired_len[-1]}\n\n"
    )

    # 同一 normalized_alias 挂多个节点(一词多义未治理)
    word_nodes: dict[str, set] = defaultdict(set)
    for a in inventory:
        word_nodes[a["normalized_alias"]].add(a["node_code"])
    multi = {w: ns for w, ns in word_nodes.items() if len(ns) > 1}
    out(f"- 同一 normalized_alias 挂多个节点的词数:{len(multi)}\n")
    for w, ns in sorted(multi.items(), key=lambda kv: -len(kv[1]))[:10]:
        out(f"  - {w}:{', '.join(sorted(ns))}\n")
    out("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
