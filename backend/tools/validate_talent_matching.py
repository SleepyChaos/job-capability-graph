import argparse
import json
from datetime import datetime
from pathlib import Path
from time import perf_counter

from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.modules.talent.models import (
    CandidateLearningPath,
    CandidateMatchGap,
    CandidateMatchResult,
    CandidateMatchRun,
    CandidateProfileVersion,
    CandidateSkillEvidence,
)
from app.modules.talent.service import (
    answer_profile_question,
    create_learning_path,
    create_profile_draft,
    create_profile_version,
    publish_profile,
    run_matching,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="验证简历画像到发展路径的 P0 闭环")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with SessionLocal() as session:
        report = build_report(session)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False))


def build_report(session) -> dict:
    started = perf_counter()
    draft = create_profile_draft(
        session,
        source_name="P0闭环验证简历.txt",
        mime_type="text/plain",
        input_type_code="txt",
        content_text=(
            "姓名：林舟\n求职意向：具身智能算法工程师\n硕士·控制科学与工程\n"
            "负责机器人项目中的Python、C++、ROS、SLAM算法开发、传感器融合和真机调试，"
            "完成定位误差与运行稳定性验证。"
        ),
    )
    first = answer_profile_question(
        session,
        version_code=draft["version_code"],
        answer_text="主导SLAM与传感器融合模块，负责代码、联调和定位误差验证。",
    )
    second = answer_profile_question(
        session,
        version_code=draft["version_code"],
        answer_text="偏好工程交付、系统联调和真机验证。",
    )
    confirmed = publish_profile(session, version_code=draft["version_code"])
    match = run_matching(session, version_code=draft["version_code"])
    if not match["results"]:
        raise SystemExit("真实数据库没有产生可验证的匹配结果")
    path = create_learning_path(session, result_code=match["results"][0]["result_code"])
    revised = create_profile_version(
        session,
        version_code=draft["version_code"],
        target_role_text="机器人系统集成工程师",
    )
    elapsed_ms = round((perf_counter() - started) * 1000, 2)
    original = session.scalar(
        select(CandidateProfileVersion).where(
            CandidateProfileVersion.version_code == draft["version_code"]
        )
    )
    invariants = {
        "profile_has_traceable_skill_evidence": confirmed["skill_count"] > 0
        and all(item["evidence_text"] for item in confirmed["skills"]),
        "dialogue_finishes_inside_two_to_eight_rounds": first["conversation_round_count"] == 1
        and 2 <= second["conversation_round_count"] <= 8,
        "profile_requires_user_confirmation_before_matching": confirmed["workflow_status_code"]
        == "confirmed",
        "match_score_has_replayable_dimensions": all(
            result["dimensions"] for result in match["results"]
        ),
        "missing_resume_skill_is_not_claimed_as_absent": all(
            gap["gap_type_code"] != "confirmed_missing"
            for result in match["results"]
            for gap in result["gaps"]
        ),
        "learning_steps_reference_match_gaps": all(
            step["evidence_reference"].startswith("gap:") for step in path["steps"]
        ),
        "profile_edit_creates_new_version_without_overwrite": revised["version_no"] == 2
        and original.workflow_status_code == "confirmed",
    }
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "summary": {
            "profile_version_code": confirmed["version_code"],
            "skill_count": confirmed["skill_count"],
            "conversation_round_count": confirmed["conversation_round_count"],
            "completeness_score": confirmed["completeness_score"],
            "match_run_code": match["run_code"],
            "match_result_count": match["result_count"],
            "top_match_title": match["results"][0]["job_title"],
            "top_match_score": match["results"][0]["overall_score"],
            "top_match_gap_count": len(match["results"][0]["gaps"]),
            "learning_path_code": path["path_code"],
            "learning_step_count": len(path["steps"]),
            "elapsed_ms": elapsed_ms,
            "invariants": invariants,
        },
        "database_counts": {
            "profile_versions": session.scalar(
                select(func.count()).select_from(CandidateProfileVersion)
            ),
            "skill_evidence": session.scalar(
                select(func.count()).select_from(CandidateSkillEvidence)
            ),
            "match_runs": session.scalar(select(func.count()).select_from(CandidateMatchRun)),
            "match_results": session.scalar(select(func.count()).select_from(CandidateMatchResult)),
            "match_gaps": session.scalar(select(func.count()).select_from(CandidateMatchGap)),
            "learning_paths": session.scalar(
                select(func.count()).select_from(CandidateLearningPath)
            ),
        },
        "top_match": match["results"][0],
        "learning_path": path,
    }


if __name__ == "__main__":
    main()
