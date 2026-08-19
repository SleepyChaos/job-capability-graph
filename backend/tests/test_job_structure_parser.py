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
    # 中文切成字符二元组：两句同义职责的切点不同也能对上（原先「连续汉字块」做不到）。
    assert cluster_tokens("机器人控制 ROS 2 / C++") == [
        "ros",
        "c++",
        "机器",
        "器人",
        "人控",
        "控制",
    ]
    # 英文虚词不作为特征，否则英文 JD 会靠 and/for 互相吸引成一堆。
    assert cluster_tokens("design and control for robots") == ["design", "control", "robots"]
    # 同义中文职责必须有非空交集——这正是修分词器要解决的问题。
    left = set(cluster_tokens("负责具身智能机器人运动控制算法的设计与实现"))
    right = set(cluster_tokens("负责人形机器人运动控制算法开发与调优"))
    assert {"运动", "控制", "算法", "机器", "器人"} <= left & right
