from copy import deepcopy

import pytest

from app.modules.graph.inference import GraphInferenceError, infer_graph_relations


def _source_graph() -> dict:
    return {
        "metadata": {"generatedAt": "2026-08-27T00:00:00+00:00"},
        "technologyNodes": [
            {"id": "t-l1", "name": "智能算法", "level": "L1", "parentId": ""},
            {"id": "t-l2", "name": "控制算法", "level": "L2", "parentId": "t-l1"},
            {"id": "t-l3", "name": "模型预测控制", "level": "L3", "parentId": "t-l2"},
            {"id": "t-l4-a", "name": "MPC", "level": "L4", "parentId": "t-l3"},
            {"id": "t-l4-b", "name": "Model Predictive Control", "level": "L4", "parentId": "t-l3"},
        ],
        "standardRoles": [
            {"id": "role-control", "name": "运动控制算法工程师"},
            {"id": "role-test", "name": "机器人测试工程师"},
        ],
        "jobs": [
            {
                "id": "job-1",
                "occId": "O00001",
                "standardRoleId": "role-control",
                "technologyTermIds": ["t-l4-a"],
            },
            {
                "id": "job-2",
                "occId": "O00002",
                "standardRoleId": "role-control",
                "technologyTermIds": ["t-l4-b"],
            },
            {
                "id": "job-3",
                "occId": "O00003",
                "standardRoleId": "role-control",
                "technologyTermIds": [],
            },
            {
                "id": "job-4",
                "occId": "O00004",
                "standardRoleId": "role-test",
                "technologyTermIds": ["t-l4-a"],
            },
        ],
    }


def test_r1_inherits_l4_to_all_ancestors_without_rewriting_facts():
    graph = _source_graph()
    original = deepcopy(graph)

    result = infer_graph_relations(graph, generated_at="2026-09-01T00:00:00+00:00")

    job_1_targets = {
        relation["targetId"]
        for relation in result["jdTechnologyInheritance"]
        if relation["sourceId"] == "job-1"
    }
    assert job_1_targets == {"t-l3", "t-l2", "t-l1"}
    assert all(
        relation["targetLevel"] != "L4"
        for relation in result["jdTechnologyInheritance"]
    )
    l1_relation = next(
        relation
        for relation in result["jdTechnologyInheritance"]
        if relation["sourceId"] == "job-1" and relation["targetId"] == "t-l1"
    )
    assert l1_relation["path"] == ["t-l4-a", "t-l3", "t-l2", "t-l1"]
    assert l1_relation["evidenceJdIds"] == ["job-1"]
    assert graph == original


def test_r2_aggregates_unique_supporting_jobs_and_uses_all_role_jobs_for_coverage():
    result = infer_graph_relations(_source_graph(), generated_at="2026-09-01T00:00:00+00:00")

    relation = next(
        item
        for item in result["standardRoleTechnologyRelations"]
        if item["sourceId"] == "role-control" and item["targetId"] == "t-l3"
    )
    assert relation["sourceName"] == "运动控制算法工程师"
    assert relation["targetName"] == "模型预测控制"
    assert relation["supportCount"] == 2
    assert relation["roleJdCount"] == 3
    assert relation["coverage"] == pytest.approx(2 / 3, abs=1e-6)
    assert relation["evidenceJdIds"] == ["job-1", "job-2"]
    assert relation["evidenceOccIds"] == ["O00001", "O00002"]
    assert relation["supportTermIds"] == ["t-l4-a", "t-l4-b"]
    assert relation["inferenceBasis"] == "r1_inherited"


def test_r2_keeps_direct_l4_and_inherited_relations_distinguishable():
    result = infer_graph_relations(_source_graph(), generated_at="2026-09-01T00:00:00+00:00")

    direct = next(
        item
        for item in result["standardRoleTechnologyRelations"]
        if item["sourceId"] == "role-control" and item["targetId"] == "t-l4-a"
    )
    inherited = next(
        item
        for item in result["standardRoleTechnologyRelations"]
        if item["sourceId"] == "role-control" and item["targetId"] == "t-l2"
    )
    assert direct["inferenceBasis"] == "direct_l4"
    assert inherited["inferenceBasis"] == "r1_inherited"


def test_hierarchy_cycle_stops_inference_instead_of_publishing_unsafe_relations():
    graph = _source_graph()
    graph["technologyNodes"][0]["parentId"] = "t-l3"

    with pytest.raises(GraphInferenceError, match="cycle detected"):
        infer_graph_relations(graph)


def test_duplicate_technology_id_is_safe_only_when_hierarchy_is_identical():
    graph = _source_graph()
    graph["technologyNodes"].append(
        {"id": "t-l4-a", "name": "M.P.C.", "level": "L4", "parentId": "t-l3"}
    )

    result = infer_graph_relations(graph)

    assert result["metadata"]["sourceTechnologyNodeCount"] == 6
    assert result["metadata"]["uniqueTechnologyNodeCount"] == 5
    assert result["metadata"]["duplicateTechnologyRowCount"] == 1
    assert result["metadata"]["warningCount"] == 1

    graph["technologyNodes"][-1]["parentId"] = "t-l2"
    with pytest.raises(GraphInferenceError, match="conflicting hierarchy"):
        infer_graph_relations(graph)
