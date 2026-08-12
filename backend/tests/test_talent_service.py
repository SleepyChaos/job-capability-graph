from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from test_clustering_service import _seed_cluster_fixture

from app.db.base import Base
from app.modules.clustering.service import run_full_clustering
from app.modules.talent.models import CandidateMatchDimensionResult, CandidateProfileVersion
from app.modules.talent.service import (
    answer_profile_question,
    create_learning_path,
    create_profile_draft,
    create_profile_version,
    publish_profile,
    run_matching,
)
from app.modules.taxonomy.models import TechnologyAlias, TechnologyNode


def test_candidate_profile_match_gap_and_learning_path_are_version_bound() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        parse_run_code = _seed_cluster_fixture(session)
        technology = session.scalar(select(TechnologyNode).where(TechnologyNode.level_code == "L3"))
        session.add(
            TechnologyAlias(
                technology_node_id=technology.technology_node_id,
                source_spreadsheet_row_id=1,
                alias_text="合成机器人控制",
                normalized_alias="合成机器人控制",
                alias_type_code="standard_name",
                is_matchable=True,
            )
        )
        session.commit()
        run_full_clustering(session, parse_run_code=parse_run_code)

        draft = create_profile_draft(
            session,
            source_name="林舟_合成简历.txt",
            mime_type="text/plain",
            input_type_code="txt",
            content_text=(
                "姓名：林舟\n求职意向：机器人控制算法工程师\n硕士·控制科学与工程\n"
                "负责合成机器人控制项目，实现控制算法开发和实验验证。"
            ),
        )
        assert draft["skill_count"] == 1
        assert draft["next_question"]["turn_no"] == 1
        first = answer_profile_question(
            session,
            version_code=draft["version_code"],
            answer_text="主导控制算法实现并完成跟踪误差验证。",
        )
        assert first["next_question"]["turn_no"] == 2
        second = answer_profile_question(
            session,
            version_code=draft["version_code"],
            answer_text="偏向工程交付和真机验证。",
        )
        assert second["can_publish"] is True
        confirmed = publish_profile(session, version_code=draft["version_code"])
        assert confirmed["workflow_status_code"] == "confirmed"

        match = run_matching(session, version_code=draft["version_code"])
        repeated_match = run_matching(session, version_code=draft["version_code"])
        assert match["result_count"] == 1
        assert repeated_match["run_code"] == match["run_code"]
        assert match["results"][0]["overall_score"] > 50
        dimensions = match["results"][0]["dimensions"]
        assert len(dimensions) == 10
        assert dimensions[0]["code"] == "required_capability_fit"
        assert {item["code"] for item in dimensions} >= {
            "required_capability_fit",
            "proficiency_fit",
            "task_semantic_fit",
            "transferable_fit",
        }
        dimension_row_count = session.scalar(
            select(func.count()).select_from(CandidateMatchDimensionResult)
        )
        assert dimension_row_count == 10
        gaps = match["results"][0]["gaps"]
        assert all(
            gap["gap_type_code"]
            in {
                "confirmed_missing",
                "evidence_insufficient",
                "depth_insufficient",
                "transferable",
                "low_confidence_requirement",
            }
            for gap in gaps
        )
        path = create_learning_path(session, result_code=match["results"][0]["result_code"])
        assert path["algorithm_version"] == "gap_path_topo_v1"
        assert all(step["evidence_reference"].startswith("gap:") for step in path["steps"])
        assert all(
            dependency < step["step_no"]
            for step in path["steps"]
            for dependency in step["depends_on"]
        )

        revised = create_profile_version(
            session,
            version_code=draft["version_code"],
            target_role_text="机器人系统工程师",
        )
        original = session.scalar(
            select(CandidateProfileVersion).where(
                CandidateProfileVersion.version_code == draft["version_code"]
            )
        )
        assert revised["version_no"] == 2
        assert revised["workflow_status_code"] == "draft"
        assert original.workflow_status_code == "confirmed"
