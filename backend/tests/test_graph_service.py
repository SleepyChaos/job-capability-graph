from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from test_clustering_service import _seed_cluster_fixture

from app.db.base import Base
from app.modules.clustering.service import run_full_clustering
from app.modules.graph.service import (
    cluster_capability_graph,
    cluster_graph_list,
    heatmap_graph,
    relation_graph,
)


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
