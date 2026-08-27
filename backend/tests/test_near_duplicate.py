from app.modules.extraction.near_duplicate import (
    hamming_distance,
    near_duplicate_clusters,
    simhash_text,
)

BASE_TEXT = (
    "负责机器人感知算法开发，完成多传感器融合与定位模块，"
    "要求熟悉C++与ROS2，具备SLAM项目经验，参与真机联调与性能优化。"
)


def test_simhash_stable_and_similar_texts_close() -> None:
    first = simhash_text(BASE_TEXT)
    assert first == simhash_text(BASE_TEXT)
    near_copy = simhash_text(BASE_TEXT.replace("性能优化", "性能调优"))
    assert hamming_distance(first, near_copy) <= 6


def test_simhash_distant_texts_far() -> None:
    other = simhash_text(
        "招聘财务主管，负责月度结账、预算管理与税务申报，要求五年以上制造业财务经验。"
    )
    assert hamming_distance(simhash_text(BASE_TEXT), other) > 6


def test_near_duplicate_clusters_only_groups_reposts() -> None:
    items = [
        (1, BASE_TEXT),
        (2, BASE_TEXT.replace("性能优化", "性能调优")),
        (3, "招聘财务主管，负责月度结账、预算管理与税务申报，要求五年以上制造业财务经验。"),
    ]
    clusters = near_duplicate_clusters(items)
    assert len(clusters) == 1
    keys = {key for key, _similarity in clusters[0]}
    assert keys == {1, 2}
    similarities = dict(clusters[0])
    assert similarities[1] == 1.0
    assert similarities[2] >= 0.9
