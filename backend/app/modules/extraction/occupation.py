"""职能岗位判别：把非具身智能技术岗挡在下游聚合之外（窗口 B）。

**为什么不用技术证据条数**：窗口 B 的实测显示，证据条数门槛无法区分非技术岗与
低证据技术岗——零证据的非技术岗本来就不产生误报，过滤它们对证据质量毫无改变；
而真正产生误报的非技术岗（销售/产品/采购）证据条数与低证据技术岗完全重叠，
提高门槛只能等比例地牺牲召回。证据条数门槛的价值在**聚类形态**（碎片化），
不在证据质量，两者必须分开看。

**这里用职位名称的职能词**：招聘语料的岗位名高度模式化，职能类别（商务/产品职能/
制造工艺/IT运维）在名称里几乎总是显式出现。这是纯机械判定：确定性、可复现、
逐条可解释，不引入 LLM（LLM 不得进入机械决策路径）。

判定结果写入特征快照的 `exclusion_reason_json`，被判出的 JD 仍然完整保留抽取结果与
证据，只是不参与聚类与岗位画像聚合——是「不纳入统计」，不是「删数据」。

口径边界：这里判的是「**非具身智能技术岗**」，不是「非技术岗」。电镀/抛光/SMT/模具
等制造工艺岗有自己的技术性，但不属于具身智能技术能力图谱的测量对象。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

OCCUPATION_RULE_VERSION = "occupation_title_rules_v1"

# 职能词按类别组织，便于逐条追溯与后续增删。全部对 casefold 后的岗位名做子串匹配。
OCCUPATION_RULES: dict[str, tuple[str, ...]] = {
    # 商务职能：销售、客户、渠道、采购
    "commercial": (
        "销售",
        "客户经理",
        "大客户",
        "业务拓展",
        "商务拓展",
        "商务专员",
        "商务经理",
        "渠道",
        "市场经理",
        "行销",
        "商业分析",
        "资产定价",
        "资产管理",
        "采购",
        "招商",
    ),
    # 产品与职能管理：产品、项目、运营、人财法行
    "product_ops": (
        "产品经理",
        "产品运营",
        "产品总监",
        "项目经理",
        "解决方案经理",
        "流程管理",
        "体系经理",
        "运营经理",
        "服务商运营",
        "人力",
        "hrbp",
        "招聘",
        "培训师",
        "行政",
        "财务",
        "法务",
        "hse",
    ),
    # 制造工艺与质量：有技术性，但不是具身智能技术
    "manufacturing": (
        "电镀",
        "焊接",
        "抛光",
        "打磨",
        "smt",
        "贴合",
        "模具",
        "包装工程师",
        "sqe",
        "供应商质量",
        "质量工程师",
        "刀具",
        "圆刀",
        "注塑",
        "喷涂",
        "装配工",
        "产线工程师",
        "设备工程师",
        "检验",
        "品质",
        "师傅",
        "操作工",
        "普工",
    ),
    # IT 运维与安全：工程性质但与具身智能无关
    "it_ops": (
        "运维工程师",
        "网络安全",
    ),
}


@dataclass(frozen=True)
class OccupationDecision:
    """判定结果。`category` 与 `matched_term` 为 None 表示未命中任何职能词。"""

    is_embodied_technical: bool
    category: str | None
    matched_term: str | None

    @property
    def reason_code(self) -> str | None:
        if self.is_embodied_technical:
            return None
        return f"non_embodied_occupation:{self.category}"


def classify_occupation(job_title: str) -> OccupationDecision:
    """按岗位名称判断是否为具身智能技术岗。

    命中多个类别时取字典序最小的类别，保证同一输入永远得到同一结果（可重放）。
    """
    lowered = (job_title or "").casefold()
    matches = [
        (category, term)
        for category, terms in OCCUPATION_RULES.items()
        for term in terms
        if term in lowered
    ]
    if not matches:
        return OccupationDecision(is_embodied_technical=True, category=None, matched_term=None)
    category, term = min(matches)
    return OccupationDecision(is_embodied_technical=False, category=category, matched_term=term)


LANGUAGE_RULE_VERSION = "feature_language_gate_v1"

# 中文字符占比低于该值的 JD，特征管线无法给出可用表示。
MIN_CHINESE_CHARACTER_RATIO = 0.10

_CHINESE_PATTERN = re.compile(r"[\u4e00-\u9fff]")


def chinese_character_ratio(text: str) -> float:
    stripped = (text or "").strip()
    if not stripped:
        return 0.0
    return len(_CHINESE_PATTERN.findall(stripped)) / len(stripped)


def is_supported_language(jd_text: str) -> bool:
    """JD 正文是否落在特征管线支持的语种内。

    整条特征管线是面向中文语料建的：中文切字符二元组、英文只留实词。语料里 96% 是
    中文，英文 JD 拿到的是稀疏向量，只能和彼此匹配——实测它们会聚成一个 65 份的簇，
    其中 62% 是英文 JD，而其余同等规模的簇英文占比为 0。那不是一个岗位，是
    「特征管线表示不了的 JD」的残余桶，一旦被晋升为岗位就是纯粹的假阳性。

    这类 JD 与职能门一样：抽取结果与证据完整保留，只是不纳入聚类与画像聚合，
    理由逐条记进排除原因。代价是这部分岗位在图谱中没有覆盖，必须随结论声明。
    """
    return chinese_character_ratio(jd_text) >= MIN_CHINESE_CHARACTER_RATIO
