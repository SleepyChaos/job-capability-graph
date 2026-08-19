"""窗口 D：迭代重分配与相似度口径修正的回归。

重分配的价值全在「结果不再依赖 JD 进入顺序」这一条上，所以第一个测试就测它。
其余测试盯的是三处会静默退化的性质：批量应用的确定性、硬约束下的终止性、
以及不把够不上阈值的 JD 强行塞进簇。
"""

from __future__ import annotations

import random

from app.modules.clustering.algorithm import (
    ClusteringParameters,
    RawJobFeature,
    cluster_jobs,
    level_similarity,
    similarity,
)


def _job(job_id: int, title: str, tokens: tuple[str, ...], level: str | None = "middle"):
    return RawJobFeature(
        job_posting_id=job_id,
        job_code=f"job_{job_id:03d}",
        title=title,
        title_tokens=tokens,
        responsibility_tokens=tokens,
        technology_weights={token: 1.0 for token in tokens},
        domain_weights={"T1": 1.0},
        level_code=level,
        sample_weight=1.0,
    )


def _two_group_corpus() -> list[RawJobFeature]:
    """两簇明显可分的合成语料：视觉组与运控组。"""
    vision = ("视觉", "感知", "标定", "点云")
    motion = ("运控", "力控", "关节", "步态")
    jobs = []
    for index in range(8):
        jobs.append(_job(index, "视觉算法工程师", vision))
    for index in range(8, 16):
        jobs.append(_job(index, "运控算法工程师", motion))
    return jobs


def _partition(output) -> set[frozenset[int]]:
    groups: dict[int, set[int]] = {}
    for decision in output.decisions:
        groups.setdefault(decision.cluster_draft_id, set()).add(decision.job_posting_id)
    return {frozenset(members) for members in groups.values()}


def test_reassignment_makes_partition_independent_of_input_order() -> None:
    """重分配存在的理由：收敛后的成员集合不该随 JD 进入顺序改变。"""
    corpus = _two_group_corpus()
    parameters = ClusteringParameters(max_cluster_size=100)

    shuffled = list(corpus)
    random.Random(20260819).shuffle(shuffled)

    assert _partition(cluster_jobs(corpus, parameters)) == _partition(
        cluster_jobs(shuffled, parameters)
    )


def test_disabling_reassignment_falls_back_to_single_pass() -> None:
    """0 轮必须退回单遍贪心，否则无法与历史运行对照。"""
    corpus = _two_group_corpus()
    output = cluster_jobs(corpus, ClusteringParameters(max_reassign_rounds=0))

    assert output.reassign_rounds == ()
    assert output.converged
    assert not output.oscillation_detected


def test_convergence_trace_is_recorded_and_terminates() -> None:
    corpus = _two_group_corpus()
    output = cluster_jobs(corpus, ClusteringParameters(max_reassign_rounds=10))

    assert output.reassign_stats["round_count"] <= 10
    assert output.converged or output.oscillation_detected
    # 逐轮记录必须连号，否则收敛过程不可复核。
    assert [item.round_no for item in output.reassign_rounds] == list(
        range(1, len(output.reassign_rounds) + 1)
    )


def test_reassignment_is_deterministic_across_repeated_runs() -> None:
    corpus = _two_group_corpus()
    parameters = ClusteringParameters()
    first = cluster_jobs(corpus, parameters)
    second = cluster_jobs(corpus, parameters)

    assert _partition(first) == _partition(second)
    assert first.reassign_stats == second.reassign_stats


def test_max_cluster_size_is_respected_after_reassignment() -> None:
    """硬约束会破坏 Lloyd 的单调性，但不能被违反。"""
    corpus = _two_group_corpus()
    output = cluster_jobs(corpus, ClusteringParameters(max_cluster_size=3))

    assert all(len(cluster.members) <= 3 for cluster in output.clusters)
    assert output.converged or output.oscillation_detected


def test_low_similarity_jobs_are_not_force_assigned() -> None:
    """够不上阈值的离群 JD 留在原处，不制造虚假归属。"""
    corpus = _two_group_corpus()
    corpus.append(_job(99, "财务分析师", ("预算", "报表", "税务", "审计")))
    output = cluster_jobs(corpus, ClusteringParameters())

    outlier_cluster = next(
        decision.cluster_draft_id
        for decision in output.decisions
        if decision.job_posting_id == 99
    )
    members = {
        decision.job_posting_id
        for decision in output.decisions
        if decision.cluster_draft_id == outlier_cluster
    }
    assert members == {99}


def test_every_job_keeps_exactly_one_cluster() -> None:
    """重建簇时若漏掉或重复成员，后续的谱系与画像都会错，且不会报错。"""
    corpus = _two_group_corpus()
    output = cluster_jobs(corpus, ClusteringParameters())

    assigned = [decision.job_posting_id for decision in output.decisions]
    assert sorted(assigned) == sorted(job.job_posting_id for job in corpus)
    from_clusters = [
        member.raw.job_posting_id for cluster in output.clusters for member in cluster.members
    ]
    assert sorted(from_clusters) == sorted(assigned)


def test_similarity_scale_reaches_one_without_the_dead_scenario_channel() -> None:
    """摘掉恒为 0 的 scenario 通道后满分回到 1.0，阈值语义才成立。"""
    corpus = [_job(index, "视觉算法工程师", ("视觉", "感知")) for index in range(4)]
    output = cluster_jobs(corpus, ClusteringParameters())
    cluster = output.clusters[0]
    score = similarity(cluster.members[0], cluster)

    assert "scenario" not in score.breakdown
    assert score.total > 0.99


def test_level_similarity_is_ordinal_not_binary() -> None:
    """相邻层级不该与跨两级同样得 0 分。"""
    assert level_similarity("middle", "middle") == 1.0
    assert level_similarity("junior", "middle") == 0.5
    assert level_similarity("junior", "senior") == 0.0
    assert level_similarity(None, "senior") == 0.0


def test_algorithm_version_bump_keeps_cluster_lineage(monkeypatch) -> None:
    """算法升版不该让全部簇失去前身。

    延续与否由成员集合的 Jaccard 判定，与算法内部无关。若前身查询按算法版本过滤，
    每次升版都会让所有簇判为 born、所有岗位被当成新岗位重建——实测 v2→v3 那次升版
    出现了 515 born / 0 continued，而下一次同版本运行是 515 continued（重叠度 0.998），
    证明簇本身没变，断裂纯粹是过滤条件造成的。
    """
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session

    from app.db.base import Base
    from app.modules.clustering import service
    from app.modules.clustering.models import JobClusterLineage
    from app.modules.clustering.service import run_full_clustering
    from tests.test_clustering_service import _seed_cluster_fixture

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        parse_run_code = _seed_cluster_fixture(session)
        run_full_clustering(session, parse_run_code=parse_run_code)

        # 升一次算法版本后重跑同一份输入：簇成员没变，谱系必须仍然接得上。
        monkeypatch.setattr(service, "ALGORITHM_VERSION", "baseline_sparse_multiview_vNEXT")
        run_full_clustering(session, parse_run_code=parse_run_code)

        edges = list(session.scalars(select(JobClusterLineage)))
        continued = [row for row in edges if row.lineage_type_code == "continued"]
        assert continued, f"升版后谱系全断：{[row.lineage_type_code for row in edges]}"
        # 跨版本的谱系边要能被认出来，否则下游分不清「真实演化」与「换算法」。
        assert any("跨算法版本比较" in (row.explanation_text or "") for row in continued)
