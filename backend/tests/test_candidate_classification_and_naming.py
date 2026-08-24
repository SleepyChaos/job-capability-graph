"""候选分类与命名的单元测试。

覆盖三处新行为：库缺失与真新岗位的区分、命名时的应用域越界拦截、
以及机械占位名的唯一性——这三处都是靠约定成立的，没有测试就会悄悄退化。
"""

from app.modules.discovery.service import (
    _classify_candidate,
    _combination_cohesion,
    _evidence_completeness,
    _mechanical_name,
    _name_asserts_unsupported_domain,
)


def foresight_block(*crossed: bool) -> dict:
    return {"directions": [{"crossed": item} for item in crossed]}


# ── 分类 ────────────────────────────────────────────────────────────────


def test_high_coverage_stays_existing_role():
    assert _classify_candidate(0.80, foresight_block(True), "budding") == "existing_role"
    assert _classify_candidate(0.50, foresight_block(True), "budding") == "role_evolution"


def test_mature_uncovered_combination_is_a_library_gap():
    """技术方向全部已跨门槛 + 支撑量成熟 → 是我们库里缺的成熟岗位，不是新岗位。

    实测里电机与驱动工程师（51 份 JD、23 家企业）就落在这一档：岗位真实存在
    几十年，只是岗位库没收录它。
    """
    assert _classify_candidate(0.20, foresight_block(True, True), "budding") == "library_gap"


def test_immature_technology_keeps_it_a_potential_new_role():
    """只要有一个技术方向还没跨过岗位化门槛，就仍是真·潜在新岗位。"""
    assert (
        _classify_candidate(0.20, foresight_block(True, False), "budding")
        == "potential_new_role"
    )


def test_thin_support_keeps_it_a_potential_new_role():
    """技术都成熟但支撑量没到 budding，还不足以断言「市场上已有这个岗位」。"""
    assert (
        _classify_candidate(0.20, foresight_block(True), "potential") == "potential_new_role"
    )


def test_missing_foresight_falls_back_to_potential_new_role():
    """没有前瞻信息时不能声称是库缺失——库缺失的判据正是「技术都已跨门槛」。"""
    assert _classify_candidate(0.20, {"directions": []}, "budding") == "potential_new_role"


# ── 命名的应用域越界 ────────────────────────────────────────────────────


def test_unsupported_application_domain_is_rejected():
    allowed = {"VLA端到端大模型", "大模型推理服务与训练加速"}
    assert _name_asserts_unsupported_domain("自动驾驶大模型训练优化工程师", allowed) == "自动驾驶"


def test_domain_is_allowed_when_the_technologies_support_it():
    allowed = {"自动驾驶世界模型", "世界模型与预测推理"}
    assert _name_asserts_unsupported_domain("自动驾驶世界模型工程师", allowed) is None


def test_grounded_name_passes():
    allowed = {"推理引擎与端侧部署", "GPU并行计算与算子优化"}
    assert _name_asserts_unsupported_domain("高性能算子库开发工程师", allowed) is None


# ── 机械占位名 ──────────────────────────────────────────────────────────


def test_mechanical_name_keeps_every_technology():
    """丢技术会让不同组合拼出同名——这正是 46 组重名的来源之一。"""
    two = _mechanical_name(["运动控制(通用)", "电机与驱动"])
    three = _mechanical_name(["运动控制(通用)", "电机与驱动", "实时工业总线"])
    assert two != three
    assert "实时工业总线" in three


def test_mechanical_name_separator_does_not_occur_inside_technology_names():
    """技术名自带「与」，用它当连接符会让边界消失。"""
    name = _mechanical_name(["推理引擎与端侧部署", "GPU并行计算与算子优化"])
    assert name == "推理引擎与端侧部署·GPU并行计算与算子优化工程师"


def test_mechanical_name_handles_the_empty_case():
    assert _mechanical_name([]) == "未命名候选岗位"


# ── 两个此前恒为常量的评分维度 ──────────────────────────────────────────


def test_cohesion_separates_incidental_pairings_from_real_bundles():
    """内聚度问的是「技术真的成套出现，还是搭了高频技术的顺风车」。"""
    frequency = {1: 400, 2: 35}
    incidental = _combination_cohesion((1, 2), support=30, frequency=frequency)
    bundled = _combination_cohesion((2,), support=30, frequency=frequency)
    assert incidental < 0.1
    assert bundled > 0.8


def test_cohesion_is_zero_without_support_or_frequency():
    assert _combination_cohesion((1,), support=0, frequency={1: 10}) == 0.0
    assert _combination_cohesion((), support=5, frequency={}) == 0.0
    assert _combination_cohesion((9,), support=5, frequency={1: 10}) == 0.0


class _Evidence:
    def __init__(self, evidence_jobs: int, orgs: int, sources: int):
        self.evidence_job_ids = dict.fromkeys(range(evidence_jobs), 1)
        self.organization_ids = set(range(orgs))
        self.source_ids = set(range(sources))


def test_completeness_measures_breadth_not_volume():
    """堆再多 JD 也补不齐缺失的证据类别——这正是旧算法恒为 1.0 的原因。"""
    many_jobs_one_source = _evidence_completeness(
        evidence=_Evidence(evidence_jobs=60, orgs=1, sources=1),
        application_count=0,
        has_real_responsibility=False,
        milestone_backed=False,
    )
    balanced = _evidence_completeness(
        evidence=_Evidence(evidence_jobs=5, orgs=3, sources=2),
        application_count=2,
        has_real_responsibility=True,
        milestone_backed=True,
    )
    assert many_jobs_one_source == 0.2
    assert balanced == 1.0
