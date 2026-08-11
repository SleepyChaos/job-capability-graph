from app.modules.clustering.algorithm import (
    ClusteringParameters,
    RawJobFeature,
    cluster_jobs,
)


def test_sparse_multiview_clustering_is_deterministic_and_keeps_top_candidates() -> None:
    features = [
        _feature(
            1,
            "J1",
            "机器人感知算法工程师",
            ("感知", "算法"),
            ("视觉", "模型"),
            {"T1.01": 1.0},
            {"T1": 1.0},
        ),
        _feature(
            2,
            "J2",
            "机器人视觉算法工程师",
            ("视觉", "算法"),
            ("视觉", "模型"),
            {"T1.01": 1.0},
            {"T1": 1.0},
        ),
        _feature(
            3,
            "J3",
            "机械结构工程师",
            ("机械", "结构"),
            ("结构", "设计"),
            {"T4.01": 1.0},
            {"T4": 1.0},
        ),
        _feature(
            4,
            "J4",
            "机械设计工程师",
            ("机械", "设计"),
            ("结构", "设计"),
            {"T4.01": 1.0},
            {"T4": 1.0},
        ),
    ]
    parameters = ClusteringParameters(assign_threshold=0.32, grey_threshold=0.20)

    first = cluster_jobs(features, parameters)
    second = cluster_jobs(list(reversed(features)), parameters)

    first_members = sorted(
        sorted(item.raw.job_code for item in cluster.members) for cluster in first.clusters
    )
    second_members = sorted(
        sorted(item.raw.job_code for item in cluster.members) for cluster in second.clusters
    )
    assert first_members == second_members == [["J1", "J2"], ["J3", "J4"]]
    assert all(decision.top_candidates for decision in first.decisions)
    assert all(len(decision.top_candidates) <= 3 for decision in first.decisions)


def test_low_similarity_job_starts_new_cluster_instead_of_forced_assignment() -> None:
    output = cluster_jobs(
        [
            _feature(1, "J1", "控制算法", ("控制",), ("轨迹",), {"T1.01": 1.0}, {"T1": 1.0}),
            _feature(2, "J2", "供应链采购", ("采购",), ("供应商",), {}, {}),
        ],
        ClusteringParameters(assign_threshold=0.44, grey_threshold=0.30),
    )

    assert len(output.clusters) == 2
    assert {item.status_code for item in output.decisions} == {"new_cluster"}


def _feature(
    job_id: int,
    code: str,
    title: str,
    title_tokens: tuple[str, ...],
    responsibility_tokens: tuple[str, ...],
    technology_weights: dict[str, float],
    domain_weights: dict[str, float],
) -> RawJobFeature:
    return RawJobFeature(
        job_posting_id=job_id,
        job_code=code,
        title=title,
        title_tokens=title_tokens,
        responsibility_tokens=responsibility_tokens,
        technology_weights=technology_weights,
        domain_weights=domain_weights,
        level_code="middle",
        sample_weight=1.0,
    )
