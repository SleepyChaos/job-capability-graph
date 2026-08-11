from app.modules.extraction.job_structure import JobStructureParser, cluster_tokens, task_parts


def test_chinese_inline_headings_and_numbered_items() -> None:
    text = (
        "工作职责 负责机器人控制算法开发；参与遥操作数据采集 "
        "任职资格 1、熟悉ROS 2与C++。2、有强化学习经验者优先。"
    )
    segments = JobStructureParser().parse(text)

    assert [item.segment_type for item in segments] == [
        "responsibility",
        "responsibility",
        "required",
        "bonus",
    ]
    assert all(text[item.start_offset : item.end_offset] == item.text for item in segments)


def test_english_sections_do_not_treat_company_about_as_job_fact() -> None:
    text = (
        "About us\nWe are an AI research company.\n"
        "Responsibilities\n- Build multimodal robot learning systems.\n"
        "- Lead model evaluation.\n"
        "Minimum qualifications\n3 years of Python experience.\n"
        "Preferred qualifications\nExperience with ROS is preferred."
    )
    segments = JobStructureParser().parse(text)

    assert [item.segment_type for item in segments] == [
        "responsibility",
        "responsibility",
        "required",
        "bonus",
    ]


def test_unheaded_text_uses_conservative_markers() -> None:
    text = "负责机械臂运动规划开发。熟悉C++并具备三年经验。这里是一段普通介绍。"
    segments = JobStructureParser().parse(text)

    assert [item.segment_type for item in segments] == [
        "responsibility",
        "required",
        "unknown",
    ]


def test_task_parts_and_cluster_tokens() -> None:
    action, task_object, expected = task_parts("负责开发机器人控制系统，确保实时稳定运行")

    assert action == "负责"
    assert task_object == "开发机器人控制系统"
    assert expected == "实时稳定运行"
    assert cluster_tokens("机器人控制 ROS 2 / C++") == ["ros", "c++", "机器人控制"]
