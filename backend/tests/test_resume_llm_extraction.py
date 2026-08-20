from app.infrastructure.llm import LLMResult
from app.modules.talent import resume_extraction

RESUME_TEXT = (
    "姓名：林舟\n"
    "求职意向：机器人算法工程师\n"
    "教育经历：华中科技大学 硕士 控制科学与工程\n"
    "工作经历：星云机器人 算法实习生，负责感知模块开发。\n"
    "项目经历：移动机器人导航项目，使用 PyTorch 完成模型训练与验证。\n"
)


def _result(payload: dict) -> LLMResult:
    return LLMResult(
        model="deepseek-test",
        prompt_version=resume_extraction.PROMPT_VERSION,
        content="",
        parsed_json=payload,
    )


def test_deepseek_resume_extraction_accepts_only_source_locked_facts(monkeypatch) -> None:
    monkeypatch.setattr(
        resume_extraction,
        "generate",
        lambda **_: _result(
            {
                "name": {"value": "林舟", "evidence_quote": "姓名：林舟"},
                "target_role": {
                    "value": "机器人算法工程师",
                    "evidence_quote": "求职意向：机器人算法工程师",
                },
                "education": [
                    {
                        "school": "华中科技大学",
                        "degree": "硕士",
                        "major": "控制科学与工程",
                        "period": "",
                        "evidence_quote": "教育经历：华中科技大学 硕士 控制科学与工程",
                    }
                ],
                "work_experiences": [
                    {
                        "company": "星云机器人",
                        "role": "算法实习生",
                        "period": "",
                        "summary": "负责感知模块开发",
                        "evidence_quote": "工作经历：星云机器人 算法实习生，负责感知模块开发。",
                    }
                ],
                "projects": [
                    {
                        "name": "移动机器人导航项目",
                        "role": "",
                        "summary": "使用 PyTorch 完成模型训练与验证",
                        "evidence_quote": (
                            "项目经历：移动机器人导航项目，使用 PyTorch 完成模型训练与验证。"
                        ),
                    }
                ],
                "skills": [
                    {
                        "raw_name": "PyTorch",
                        "normalized_keyword": "PyTorch深度学习框架",
                        "proficiency": "未说明",
                        "evidence_quote": (
                            "项目经历：移动机器人导航项目，使用 PyTorch 完成模型训练与验证。"
                        ),
                    }
                ],
            }
        ),
    )

    facts = resume_extraction.extract_resume_facts(RESUME_TEXT)

    assert facts["parser_version"] == "candidate_profile_deepseek_v1"
    assert facts["display_name"] == "林舟"
    assert facts["target_role"] == "机器人算法工程师"
    assert facts["structured_facts"]["education"][0]["school"] == "华中科技大学"
    assert facts["structured_facts"]["projects"][0]["name"] == "移动机器人导航项目"
    assert facts["skill_mentions"][0]["raw_name"] == "PyTorch"
    assert facts["extraction"]["method"] == "deepseek_evidence_locked"


def test_hallucinated_llm_facts_are_rejected_and_rules_take_over(monkeypatch) -> None:
    monkeypatch.setattr(
        resume_extraction,
        "generate",
        lambda **_: _result(
            {
                "name": {"value": "不存在的人", "evidence_quote": "姓名：林舟"},
                "target_role": {"value": "", "evidence_quote": ""},
                "education": [],
                "work_experiences": [],
                "projects": [],
                "skills": [
                    {
                        "raw_name": "TensorFlow",
                        "normalized_keyword": "TensorFlow",
                        "proficiency": "精通",
                        "evidence_quote": "精通 TensorFlow",
                    }
                ],
            }
        ),
    )

    facts = resume_extraction.extract_resume_facts(RESUME_TEXT)

    assert facts["parser_version"] == "candidate_profile_rules_v1"
    assert facts["display_name"] == "林舟"
    assert facts["skill_mentions"] is None
    assert facts["extraction"]["method"] == "rules_fallback"


def test_resume_prompt_forbids_sensitive_inference_and_technology_ids() -> None:
    prompt = resume_extraction._system_prompt()

    assert "不可信数据" in prompt
    assert "不推断人格" in prompt
    assert "不得输出技术编码" in prompt


def test_resume_extraction_passes_dedicated_long_timeout(monkeypatch) -> None:
    """重负载抽取必须使用专用长超时，防止默认 30s 误触发规则降级。"""
    captured: dict = {}

    def fake_generate(**kwargs):
        captured.update(kwargs)
        return _result(
            {
                "name": {"value": "林舟", "evidence_quote": "姓名：林舟"},
                "target_role": {"value": "", "evidence_quote": ""},
                "education": [],
                "work_experiences": [],
                "projects": [],
                "skills": [],
            }
        )

    monkeypatch.setattr(resume_extraction, "generate", fake_generate)

    resume_extraction.extract_resume_facts(RESUME_TEXT)

    assert captured["timeout_seconds"] == resume_extraction.LLM_TIMEOUT_SECONDS
    assert captured["timeout_seconds"] > 30
    assert captured["json_mode"] is True

