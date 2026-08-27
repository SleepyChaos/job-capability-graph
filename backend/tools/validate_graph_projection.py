import argparse
import json
from datetime import datetime
from pathlib import Path
from time import perf_counter

from app.db.session import SessionLocal
from app.modules.graph.service import (
    cluster_capability_graph,
    cluster_graph_list,
    heatmap_graph,
    relation_graph,
)


def timed(callable_):
    started = perf_counter()
    result = callable_()
    return result, round((perf_counter() - started) * 1000, 2)


def main() -> None:
    parser = argparse.ArgumentParser(description="验证三类能力图谱 P0 投影不变量")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with SessionLocal() as session:
        report = build_report(session)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False))


def build_report(session) -> dict:
    relations, relation_ms = timed(lambda: relation_graph(session))
    clusters, cluster_list_ms = timed(lambda: cluster_graph_list(session))
    if not clusters["items"]:
        raise SystemExit("当前聚类快照没有可验证的有效岗位聚类")
    cluster_code = clusters["items"][0]["stable_cluster_code"]
    cluster_detail, cluster_detail_ms = timed(
        lambda: cluster_capability_graph(session, stable_cluster_code=cluster_code)
    )
    heatmap, heatmap_ms = timed(lambda: heatmap_graph(session))
    domain_detail, domain_detail_ms = timed(lambda: heatmap_graph(session, domain_code="T1"))

    node_ids = {item["id"] for item in relations["role_nodes"] + relations["capability_nodes"]}
    data_versions = {
        relations["data_version"],
        clusters["data_version"],
        cluster_detail["data_version"],
        heatmap["data_version"],
        domain_detail["data_version"],
    }
    target_dates = {
        relations["target_date"],
        clusters["target_date"],
        cluster_detail["target_date"],
        heatmap["target_date"],
        domain_detail["target_date"],
    }
    global_rows = heatmap["global_rows"]
    detail_series = domain_detail["detail_series"]
    all_cells = [cell for row in global_rows for cell in row["cells"]]
    invariants = {
        "all_relation_edges_have_existing_endpoints": all(
            edge["source"] in node_ids and edge["target"] in node_ids for edge in relations["edges"]
        ),
        "relation_projection_respects_p0_limits": len(relations["role_nodes"]) <= 12
        and all(
            sum(edge["source"] == node["id"] for edge in relations["edges"]) <= 8
            for node in relations["role_nodes"]
        ),
        "every_relation_has_traceable_job_codes": bool(relations["edges"])
        and all(edge["evidence_job_codes"] for edge in relations["edges"]),
        "cluster_metrics_keep_importance_and_recency_separate": bool(cluster_detail["capabilities"])
        and all(
            0 <= item["importance"] <= 100 and 0 <= item["recent_activity"] <= 100
            for item in cluster_detail["capabilities"]
        )
        and cluster_detail["encoding"]["distance"] != cluster_detail["encoding"]["color_intensity"],
        "global_heatmap_is_exactly_21_by_15": len(global_rows) == 21
        and all(len(row["cells"]) == 15 for row in global_rows),
        "domain_heatmap_is_three_by_15_per_technology": bool(detail_series)
        and all(
            len(item["rows"]) == 3 and all(len(row) == 15 for row in item["rows"])
            for item in detail_series
        ),
        "heatmap_uses_fixed_45_day_window": heatmap["window"]["days"] == 45
        and len(all_cells) == 315,
        "partial_time_coverage_is_disclosed": heatmap["window"]["data_status"] == "partial"
        and bool(heatmap["window"]["warning"]),
        "all_views_share_one_frozen_snapshot": len(data_versions) == 1 and len(target_dates) == 1,
        "all_heat_cells_are_not_after_target_date": all(
            cell["metric_date"] <= heatmap["target_date"] for cell in all_cells
        ),
    }
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "summary": {
            "data_version": relations["data_version"],
            "target_date": relations["target_date"],
            "projection_version": relations["projection_version"],
            "active_cluster_count": clusters["total_active_cluster_count"],
            "preview_role_node_count": len(relations["role_nodes"]),
            "preview_capability_node_count": len(relations["capability_nodes"]),
            "preview_edge_count": len(relations["edges"]),
            "validated_cluster_code": cluster_code,
            "validated_cluster_capability_count": len(cluster_detail["capabilities"]),
            "heatmap_global_row_count": len(global_rows),
            "heatmap_detail_technology_count": len(detail_series),
            "observed_date_count": heatmap["window"]["observed_date_count"],
            "window_days": heatmap["window"]["days"],
            "invariants": invariants,
        },
        "timings_ms": {
            "relations": relation_ms,
            "cluster_list": cluster_list_ms,
            "cluster_detail": cluster_detail_ms,
            "heatmap_global": heatmap_ms,
            "heatmap_domain_detail": domain_detail_ms,
        },
        "window": heatmap["window"],
        "rendering": {
            "relations": relations["rendering"],
            "cluster": cluster_detail["encoding"],
            "heatmap": heatmap["rendering"],
        },
    }


if __name__ == "__main__":
    main()
