from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from test_clustering_service import _seed_cluster_fixture

from app.db.base import Base
from app.modules.clustering.models import JobClusteringRun, JobClusterVersion
from app.modules.clustering.service import run_full_clustering
from app.modules.graph.service import (
    cluster_capability_graph,
    cluster_graph_list,
    heatmap_graph,
    relation_graph,
    relation_graph_neighbors,
)
from app.modules.taxonomy.models import TechnologyNode


def test_graph_projections_share_governed_evidence_and_visual_ledger() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        parse_run_code = _seed_cluster_fixture(session)
        run_full_clustering(session, parse_run_code=parse_run_code)

        relations = relation_graph(session, cluster_limit=5, capabilities_per_cluster=5)
        clusters = cluster_graph_list(session, limit=5)
        cluster_code = relations["role_nodes"][0]["id"].removeprefix("cluster:")
        detail = cluster_capability_graph(
            session,
            stable_cluster_code=cluster_code,
            capability_limit=5,
        )
        heatmap = heatmap_graph(session, domain_code="T1")

        assert len(relations["role_nodes"]) == 1
        assert len(relations["capability_nodes"]) == 1
        assert relations["edges"][0]["supporting_job_count"] == 3
        assert relations["edges"][0]["coverage_rate"] == 1
        assert relations["rendering"]["fallback"] == "edge_table"
        assert relations["rendering"]["primary_route"] == "canvas_force"
        assert relations["filters"]["node_budget"] == 240
        assert relations["filters"]["cluster_limit"] == 5
        assert clusters["items"][0]["stable_cluster_code"] == cluster_code
        assert detail["capabilities"][0]["level_code"] == "L2"
        assert detail["capabilities"][0]["supporting_job_count"] == 3
        assert detail["encoding"]["distance"].startswith("inverse")
        assert len(heatmap["global_rows"]) == 21
        assert all(len(row["cells"]) == 15 for row in heatmap["global_rows"])
        assert len(heatmap["detail_series"]) == 1
        assert heatmap["detail_series"][0]["total_trigger_documents"] == 3
        assert heatmap["window"]["data_status"] == "partial"
        assert heatmap["data_version"] == relations["data_version"]


def test_relation_graph_keeps_role_filter_independent_from_capability_filter() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        parse_run_code = _seed_cluster_fixture(session)
        run_full_clustering(session, parse_run_code=parse_run_code)

        relations = relation_graph(
            session,
            cluster_domain_code="T1",
            capability_domain_code="T2",
            capability_level_code="L2",
        )

        assert len(relations["role_nodes"]) == 1
        assert relations["capability_nodes"] == []
        assert relations["edges"] == []


def test_relation_graph_keeps_governed_l2_nodes_without_current_evidence() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        parse_run_code = _seed_cluster_fixture(session)
        run_full_clustering(session, parse_run_code=parse_run_code)
        existing = session.scalar(select(TechnologyNode).where(TechnologyNode.level_code == "L2"))
        assert existing is not None
        orphan = TechnologyNode(
            taxonomy_version_id=existing.taxonomy_version_id,
            technology_code="SYNTH-T7-L2-ORPHAN",
            source_spreadsheet_row_id=existing.source_spreadsheet_row_id,
            level_code="L2",
            technology_name="暂无证据的合成能力域",
            normalized_name="暂无证据的合成能力域",
        )
        session.add(orphan)
        session.commit()

        relations = relation_graph(session, node_budget=10)
        orphan_node = next(
            node
            for node in relations["capability_nodes"]
            if node["id"] == f"technology:{orphan.technology_node_id}"
        )

        assert orphan_node["evidence_count"] == 0
        assert all(edge["target"] != orphan_node["id"] for edge in relations["edges"])


def test_relation_graph_respects_node_budget_and_support_threshold() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        parse_run_code = _seed_cluster_fixture(session)
        run_full_clustering(session, parse_run_code=parse_run_code)

        relations = relation_graph(
            session,
            node_budget=2,
            min_supporting_job_count=4,
        )

        assert len(relations["role_nodes"]) == 1
        assert len(relations["capability_nodes"]) == 1
        assert relations["capability_nodes"][0]["evidence_count"] == 0
        assert relations["edges"] == []
        assert relations["filters"]["node_budget"] == 2


def test_relation_graph_uses_budget_for_all_role_clusters_before_capabilities() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        parse_run_code = _seed_cluster_fixture(session)
        run_full_clustering(session, parse_run_code=parse_run_code)
        initial = relation_graph(session, node_budget=1000)
        run = session.scalar(select(JobClusteringRun))
        assert run is not None
        for index in range(2):
            session.add(
                JobClusterVersion(
                    clustering_run_id=run.clustering_run_id,
                    stable_cluster_code=f"JC-extra-{index}",
                    cluster_label=f"补充岗位聚类 {index}",
                    member_count=0,
                    independent_organization_count=0,
                    centroid_json={},
                    representative_job_ids_json=[],
                    cluster_status_code="active",
                )
            )
        session.commit()

        role_budget = len(initial["role_nodes"]) + 2
        relations = relation_graph(session, node_budget=role_budget, cluster_limit=1000)

        assert len(relations["role_nodes"]) == role_budget
        assert relations["capability_nodes"] == []


def test_relation_graph_focus_mode_returns_requested_cluster() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        parse_run_code = _seed_cluster_fixture(session)
        run_full_clustering(session, parse_run_code=parse_run_code)
        overview = relation_graph(session)
        focus_id = overview["role_nodes"][0]["id"]

        focused = relation_graph(session, mode="focus", focus_node_id=focus_id)

        assert [node["id"] for node in focused["role_nodes"]] == [focus_id]
        assert focused["filters"]["mode"] == "focus"


def test_relation_graph_neighbors_projects_bounded_local_neighborhood() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        parse_run_code = _seed_cluster_fixture(session)
        run_full_clustering(session, parse_run_code=parse_run_code)
        overview = relation_graph(session)
        cluster_id = overview["role_nodes"][0]["id"]

        cluster_neighbors = relation_graph_neighbors(
            session,
            node_id=cluster_id,
            neighbor_limit=1,
        )
        technology_id = cluster_neighbors["capability_nodes"][0]["id"]
        technology_neighbors = relation_graph_neighbors(
            session,
            node_id=technology_id,
            neighbor_limit=1,
        )

        assert cluster_neighbors["expansion"]["source_node_id"] == cluster_id
        assert cluster_neighbors["expansion"]["returned_neighbor_count"] == 1
        assert len(cluster_neighbors["edges"]) == 1
        assert technology_neighbors["role_nodes"][0]["id"] == cluster_id
        assert technology_neighbors["edges"][0]["target"] == technology_id
