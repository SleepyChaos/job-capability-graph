from app.modules.talent.job_graph_bridge import (
    job_graph_association,
    job_graph_overview,
    job_graph_role_detail,
    load_job_graph_bridge,
)


def test_new_job_graph_bridge_covers_v4_postings_and_roles():
    bridge = load_job_graph_bridge()

    assert bridge["metadata"]["job_count"] == 4655
    assert bridge["metadata"]["standard_role_count"] == 107

    association = job_graph_association(
        source_job_id="O00015",
        job_code="job:test",
        job_title="Staff AI Product Designer",
        company="Google DeepMind",
        required_capability_graph={"total_count": 0, "items": []},
    )

    assert association["status"] == "linked"
    assert association["standard_role"]["name"]
    assert association["hierarchy"]["cluster_code"].startswith("CL")
    assert association["portrait"] is not None
    assert association["technology_paths"]

    overview = job_graph_overview()
    assert overview["metadata"]["direction_count"] == 6
    assert overview["metadata"]["category_count"] == 17
    assert overview["metadata"]["cluster_count"] == 42
    assert len(overview["technologies"]) > 0
    assert len(overview["companies"]) > 0

    role_detail = job_graph_role_detail(association["standard_role"]["role_code"])
    assert role_detail is not None
    assert role_detail["jobs"]


def test_new_job_graph_bridge_reports_unlinked_posting_without_guessing():
    association = job_graph_association(
        source_job_id="NOT-IN-V4",
        job_code="job:unknown",
        job_title="未知岗位",
        company=None,
        required_capability_graph={"total_count": 0, "items": []},
    )

    assert association["status"] == "unlinked"
    assert association["standard_role"] is None
