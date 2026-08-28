from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from test_clustering_service import _seed_cluster_fixture

from app.db.base import Base
from app.modules.clustering.models import JobClusterVersion
from app.modules.clustering.service import run_full_clustering
from app.modules.talent.models import (
    CandidateMatchDimensionResult,
    CandidateMatchResult,
    CandidateProfileVersion,
)
from app.modules.talent.service import (
    _career_level_fit,
    _dimension_development_steps,
    _ensure_next_question,
    _jd_evidence_coverage,
    _resume_document_proficiency,
    _role_relevance_band,
    _role_title_relevance,
    _scenario_preference_fit,
    _strongest_resume_evidence,
    answer_match_evidence_question,
    answer_profile_question,
    create_learning_path,
    create_profile_draft,
    create_profile_version,
    get_match_evidence_question,
    publish_profile,
    run_matching,
    save_job_requirement_expression,
)
from app.modules.taxonomy.models import TechnologyAlias, TechnologyNode


def test_role_title_relevance_blocks_cross_occupation_false_positives() -> None:
    assert _role_title_relevance("机械工程师", "深圳 机械结构工程师") >= 0.72
    assert _role_title_relevance("机械工程师", "深圳 大客户服务经理") < 0.40
    assert _role_title_relevance("品质经理 / 质量经理", "供应商质量工程师") >= 0.72
    assert _role_title_relevance("人力资源数据分析师 / HRIS分析师", "数据平台架构师") < 0.40
    assert _role_title_relevance("人力资源数据分析师 / HRIS分析师", "HRIS实施顾问") >= 0.72
    assert _role_title_relevance("光学工程师（产品策略方向）", "产品经理") < 0.40
    assert _role_title_relevance("光学工程师（产品策略方向）", "激光雷达系统工程师") >= 0.40
    assert _role_title_relevance("实习生（技术/运营/市场方向均可）", "实习生招聘") >= 0.72
    assert _role_title_relevance("实习生（技术/运营/市场方向均可）", "技术项目经理") < 0.40
    assert _role_relevance_band(_role_title_relevance("财务BP", "高级审计员")) == 1
    assert _role_title_relevance("防爆结构工程师", "防爆结构工程师") == 1.0
    assert _role_title_relevance("防爆结构工程师", "高级结构工程师") < 0.72


def test_jd_source_evidence_prefers_specialized_defense_role() -> None:
    resume = (
        "负责防爆电气设备隔爆外壳结构设计，依据GB/T 3836、IEC 60079开展设计，"
        "主导5款产品通过Ex防爆认证。使用Ansys进行结构应力分析和耐爆压力校核，"
        "完成SolidWorks建模、BOM编制、压铸件试产与量产。"
    )
    defense_jd = (
        "负责防爆机械结构设计、强度校核和有限元分析，满足GB、IEC防爆标准；"
        "支持防爆认证，使用SolidWorks和ANSYS，负责材料选型、BOM与量产。"
    )
    robot_jd = (
        "负责多关节机器人机械设计、传动设计和关节模组选型，熟悉轴承、丝杆、"
        "齿轮和连杆；完成SolidWorks结构设计、强度校核、BOM与量产。"
    )
    defense_fit = _jd_evidence_coverage(resume, defense_jd)
    robot_fit = _jd_evidence_coverage(resume, robot_jd)
    assert defense_fit is not None and robot_fit is not None
    assert defense_fit >= 0.85
    assert defense_fit > robot_fit + 0.20


def test_strongest_resume_evidence_prefers_work_history_over_skill_list() -> None:
    resume = (
        "主导5款产品通过Ex防爆认证，并与认证机构完成整改闭环。\n技能：系统掌握ATEX/IECEx防爆标准。"
    )
    evidence = _strongest_resume_evidence(
        resume,
        ["ATEX/IECEx", "防爆认证"],
        fallback="系统掌握ATEX/IECEx防爆标准",
    )
    assert "主导5款产品通过Ex防爆认证" in evidence


def test_business_evidence_scores_sales_leadership_without_technical_taxonomy() -> None:
    resume = (
        "12年快消品及新零售行业销售管理经验，负责华东区域销售业务，下辖120人销售团队，"
        "年度目标5.2亿。重构经销商分级管理体系，与重点客户达成战略直供合作，"
        "核心经销商从40家提升至78家，区域销售额5.8亿，同比增长11.5%。"
    )
    target_jd = (
        "负责区域销售管理，制定销售策略并带领团队完成业绩目标；开发新客户，"
        "维护经销商和重点客户，推动解决方案落地。要求5年以上销售管理经验。"
    )
    unrelated_jd = "负责职业院校产教融合教学设备销售，要求5年以上教育行业经验。"
    target_fit = _jd_evidence_coverage(resume, target_jd)
    unrelated_fit = _jd_evidence_coverage(resume, unrelated_jd)
    assert target_fit is not None and unrelated_fit is not None
    assert target_fit >= 0.50
    assert target_fit > unrelated_fit + 0.30
    assert _resume_document_proficiency(resume) == 0.90


def test_business_scenario_and_level_use_confirmed_profile_evidence() -> None:
    preference = "优先AMR/AGV和工厂仓储移动机器人，也接受工业自动化场景。"
    amr_jd = "负责AMR行业区域销售、客户开发和渠道建设。"
    education_jd = "负责职业院校产教融合教学设备的区域销售。"
    assert _scenario_preference_fit(preference, amr_jd, "区域销售经理") > (
        _scenario_preference_fit(preference, education_jd, "区域销售经理")
    )
    candidate = "现任华东大区区域销售总监"
    assert _career_level_fit(candidate, ["区域销售总监"]) == 1.0
    assert _career_level_fit(candidate, ["区域销售经理"]) == 0.78


def test_resume_questions_use_current_resume_gaps_and_context() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        dimensions = {
            "job_responsibilities": [{"value": "负责算法开发"}],
            "required_skills": [{"raw_name": "ROS2"}],
            "tools_platforms": [{"value": "ROS2"}],
            "education_major": [{"major": "自动化"}],
            "work_experience": [{"company": "星云机器人"}],
            "application_scenarios": [{"value": "移动机器人"}],
            "generic_capabilities": [{"value": "跨模块协作"}],
        }
        missing_tools = {**dimensions, "tools_platforms": []}
        detailed = CandidateProfileVersion(
            candidate_profile_version_id=101,
            target_role_text="机器人算法工程师",
            preference_json={},
            fact_json={
                "structured": {
                    "projects": [{"name": "移动机器人导航项目", "role": "算法开发"}],
                    "work_experiences": [{"company": "星云机器人"}],
                    "education": [{"major": "自动化"}],
                    "profile_dimensions": missing_tools,
                },
                "resume_keywords": [
                    {"raw_name": "ROS2", "normalized_keyword": "ROS2"},
                    {"raw_name": "SLAM", "normalized_keyword": "SLAM"},
                ],
            },
        )
        detailed_question = _ensure_next_question(session, detailed)
        assert detailed_question is not None
        assert detailed_question.question_code == "tools_platforms"
        assert "机器人算法工程师" in detailed_question.question_text
        session.rollback()

        missing_education = {**dimensions, "education_major": []}
        sparse = CandidateProfileVersion(
            candidate_profile_version_id=102,
            target_role_text="机械设计工程师",
            preference_json={},
            fact_json={
                "structured": {
                    "projects": [],
                    "work_experiences": [{"company": "制造企业"}],
                    "education": [],
                    "profile_dimensions": missing_education,
                }
            },
        )
        sparse_question = _ensure_next_question(session, sparse)
        assert sparse_question is not None
        assert sparse_question.question_code == "education_major"
        assert "学历或专业" in sparse_question.question_text
        assert sparse_question.question_text != detailed_question.question_text


def test_candidate_profile_match_gap_and_learning_path_are_version_bound(monkeypatch) -> None:
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
        # Retrieval is posting-based: cluster governance state must not hide an
        # otherwise active source posting from the candidate pool.
        for cluster in session.scalars(select(JobClusterVersion)):
            cluster.cluster_status_code = "inactive"
        session.commit()

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
        assert len(draft["dialogue_history"]) == 1
        assert draft["dialogue_history"][0]["answer_text"] is None
        first = answer_profile_question(
            session,
            version_code=draft["version_code"],
            answer_text="主导控制算法实现并完成跟踪误差验证。",
        )
        assert first["next_question"]["turn_no"] == 2
        assert first["dialogue_history"][0]["answer_text"] == "主导控制算法实现并完成跟踪误差验证。"
        second = answer_profile_question(
            session,
            version_code=draft["version_code"],
            answer_text="偏向工程交付和真机验证。",
        )
        assert second["can_publish"] is True
        assert [turn["turn_no"] for turn in second["dialogue_history"]] == [1, 2]
        confirmed = publish_profile(session, version_code=draft["version_code"])
        assert confirmed["workflow_status_code"] == "confirmed"

        def fail_if_matching_calls_llm(**_: object):
            raise AssertionError("机械评分链路不得调用 LLM")

        monkeypatch.setattr("app.infrastructure.llm.generate", fail_if_matching_calls_llm)

        match = run_matching(session, version_code=draft["version_code"])
        repeated_match = run_matching(session, version_code=draft["version_code"])
        assert match["result_count"] == match["candidate_count"] == 4
        assert match["candidate_scope"] == "all_active_job_postings"
        assert match["pipeline"] == [
            "resume_parse",
            "job_jd_parse",
            "deterministic_match",
        ]
        assert match["scoring_policy"]["llm_used"] is False
        assert match["scoring_policy"]["dimension_count"] == 10
        assert repeated_match["run_code"] == match["run_code"]
        assert match["results"][0]["overall_score"] > 50
        assert match["algorithm_version"] == "r_daea_pjf_v9_business_evidence_ten_dimension"
        assert (
            match["results"][0]["score_interval"]["lower"] <= match["results"][0]["overall_score"]
        )
        assert (
            match["results"][0]["overall_score"] <= match["results"][0]["score_interval"]["upper"]
        )
        assert match["results"][0]["decision"]["status"] in {
            "safe_match",
            "safe_nonmatch",
            "needs_evidence",
            "human_review",
        }
        recommendation = match["results"][0]["recommendation"]
        assert recommendation["retrieval"]["ranking_unit"] == "job_posting"
        assert recommendation["retrieval"]["candidate_count"] == 4
        assert len({item["representative_jd"]["job_code"] for item in match["results"]}) == 4
        assert match["results"][0]["job_detail"]["jd_text"]
        assert match["results"][0]["job_detail"]["job_code"]
        assert match["results"][0]["job_detail"]["title_raw"]
        assert "employment_type" in match["results"][0]["job_detail"]
        assert "salary_text" in match["results"][0]["job_detail"]
        assert "education_text" in match["results"][0]["job_detail"]
        assert "experience_text" in match["results"][0]["job_detail"]
        assert match["results"][0]["job_detail"]["posting_status"] == "active"
        assert recommendation["requirement_expression"] is not None
        assert recommendation["requirement_proof"]["operator"] in {"AND", "MUST"}
        assert recommendation["acquisition_policy"]["llm_used_for_selection"] is False
        assert recommendation["acquisition_policy"]["reference_date"] == "2026-08-10"
        assert "minimal_improvement_sets" in recommendation
        matched_result = session.scalar(
            select(CandidateMatchResult).where(
                CandidateMatchResult.result_code == match["results"][0]["result_code"]
            )
        )
        saved_expression = save_job_requirement_expression(
            session,
            job_cluster_version_id=matched_result.job_cluster_version_id,
            expression_payload={
                "operator": "MUST",
                "technology_node_id": technology.technology_node_id,
                "hard": True,
            },
        )
        assert saved_expression["expression_version_no"] == 1
        rematch = run_matching(session, version_code=draft["version_code"])
        assert rematch["run_code"] != match["run_code"]
        assert (
            rematch["results"][0]["recommendation"]["acquisition_policy"]["requirement_source"]
            == "human_confirmed_expression"
        )
        dimensions = match["results"][0]["dimensions"]
        assert len(dimensions) == 10
        assert dimensions[0]["code"] == "required_capability_fit"
        assert {item["code"] for item in dimensions} >= {
            "required_capability_fit",
            "proficiency_fit",
            "task_semantic_fit",
            "transferable_fit",
        }
        required_graph = match["results"][0]["required_capability_graph"]
        assert required_graph["total_count"] == len(required_graph["items"])
        assert required_graph["total_count"] >= 1
        assert (
            required_graph["covered_count"]
            + required_graph["unresolved_count"]
            + required_graph["confirmed_missing_count"]
            == required_graph["total_count"]
        )
        assert all(item["path"] for item in required_graph["items"])
        assert all(
            item["path"][-1]["technology_node_id"] == item["technology_node_id"]
            for item in required_graph["items"]
        )
        rematch_graph = rematch["results"][0]["required_capability_graph"]
        assert rematch_graph["requirement_source"] == "human_confirmed_expression"
        assert any(
            item["technology_node_id"] == technology.technology_node_id
            for item in rematch_graph["items"]
        )
        dimension_row_count = session.scalar(
            select(func.count()).select_from(CandidateMatchDimensionResult)
        )
        assert dimension_row_count == (match["result_count"] + rematch["result_count"]) * 10
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
        if not gaps:
            project_dimension = session.scalar(
                select(CandidateMatchDimensionResult).where(
                    CandidateMatchDimensionResult.candidate_match_result_id
                    == matched_result.candidate_match_result_id,
                    CandidateMatchDimensionResult.dimension_code == "project_evidence_fit",
                )
            )
            project_dimension.raw_score = 83.5
            project_dimension.status_code = "interval_scored"
            session.commit()
        path = create_learning_path(session, result_code=match["results"][0]["result_code"])
        assert path["algorithm_version"] == "gap_path_topo_v2_dimension_fallback"
        assert all(
            step["evidence_reference"].startswith(("gap:", "dimension:")) for step in path["steps"]
        )
        assert all("具身智能" not in step["practice_task"] for step in path["steps"])
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


def test_dimension_development_steps_fill_taxonomy_gap_without_unknown_skill_gap() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        result = CandidateMatchResult(
            candidate_match_result_id=901,
            candidate_match_run_id=1,
            result_code="CMR-dimension-fallback",
            job_cluster_version_id=None,
            representative_job_posting_id=None,
            rank_no=1,
            overall_score=83.0,
            confidence_score=80.0,
            dimension_json=[],
            recommendation_json={},
        )
        session.add(result)
        session.add_all(
            [
                CandidateMatchDimensionResult(
                    candidate_match_result_id=901,
                    dimension_code="project_evidence_fit",
                    dimension_label="项目证据",
                    raw_score=83.5,
                    weight=0.08,
                    contribution=6.68,
                    status_code="interval_scored",
                ),
                CandidateMatchDimensionResult(
                    candidate_match_result_id=901,
                    dimension_code="bonus_capability_fit",
                    dimension_label="加分能力覆盖",
                    raw_score=50.0,
                    weight=0.10,
                    contribution=5.0,
                    status_code="neutral_unknown",
                ),
                CandidateMatchDimensionResult(
                    candidate_match_result_id=901,
                    dimension_code="transferable_fit",
                    dimension_label="可迁移能力",
                    raw_score=0.0,
                    weight=0.04,
                    contribution=0.0,
                    status_code="interval_scored",
                ),
            ]
        )
        session.flush()

        steps = _dimension_development_steps(
            session,
            result,
            start_step_no=1,
            limit=6,
            has_capability_gaps=False,
        )

        assert len(steps) == 1
        assert steps[0]["technology_name"] == "项目证据与作品集"
        assert steps[0]["gap_id"] is None
        assert steps[0]["evidence_reference"].startswith(
            "dimension:project_evidence_fit:score:83.5"
        )


def test_decision_aware_evidence_question_creates_audited_profile_version() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        parse_run_code = _seed_cluster_fixture(session)
        run_full_clustering(session, parse_run_code=parse_run_code)
        draft = create_profile_draft(
            session,
            source_name="证据不完整简历.txt",
            mime_type="text/plain",
            input_type_code="txt",
            content_text=(
                "姓名：周宁\n求职意向：机器人控制算法工程师\n"
                "硕士学历，参与过智能装备项目，当前简历未展开具体工具和个人职责。"
            ),
        )
        assert draft["skill_count"] == 0
        answer_profile_question(
            session,
            version_code=draft["version_code"],
            answer_text="参与智能装备项目并负责实验资料整理。",
        )
        answer_profile_question(
            session,
            version_code=draft["version_code"],
            answer_text="偏向工程实现与验证。",
        )
        publish_profile(session, version_code=draft["version_code"])

        first_match = run_matching(session, version_code=draft["version_code"])
        first_result = first_match["results"][0]
        assert first_result["decision"]["status"] == "needs_evidence"
        question = get_match_evidence_question(session, result_code=first_result["result_code"])
        assert question["can_answer"] is True
        assert question["llm_used_for_selection"] is False
        assert question["next_evidence_question"]["technology_name"] == "合成机器人控制"
        assert question["next_evidence_question"]["value_components"]["privacy_risk"] >= 0
        assert (
            question["next_evidence_question"]["selection_method"]
            == "one_step_expected_and_robust_voi"
        )
        assert question["next_evidence_question"]["outcome_simulations"]

        update = answer_match_evidence_question(
            session,
            result_code=first_result["result_code"],
            answer_text=(
                "2025年机器人项目中，我负责合成机器人控制算法开发，"
                "完成跟踪误差实验验证并提交代码与实验指标。"
            ),
        )
        assert update["evidence_update"]["evidence_state"] == "contextual"
        assert update["profile"]["version_no"] == 2
        assert update["profile"]["workflow_status_code"] == "confirmed"
        updated_result = update["match"]["results"][0]
        assert updated_result["overall_score"] > first_result["overall_score"]
        assert updated_result["score_interval"]["width"] < first_result["score_interval"]["width"]
        assert any(
            skill["evidence_level_code"] == "contextual" for skill in update["profile"]["skills"]
        )

        negative_update = answer_match_evidence_question(
            session,
            result_code=first_result["result_code"],
            answer_text="我没有使用过这项技术，也没有相关项目经验。",
        )
        assert negative_update["evidence_update"]["evidence_state"] == "confirmed_missing"
        negative_result = negative_update["match"]["results"][0]
        assert negative_result["decision"]["status"] == "safe_nonmatch"
        assert negative_result["score_interval"]["upper"] <= 59.0
        assert negative_result["recommendation"]["hard_constraints"]["failed"] is True
        assert negative_result["recommendation"]["next_evidence_question"] is None
