from app.modules.extraction.technology import TechnologyAliasMatcher, TechnologyPattern


def test_matcher_prefers_longest_overlap_and_respects_ascii_boundaries() -> None:
    matcher = TechnologyAliasMatcher(
        [
            TechnologyPattern(alias_id=1, normalized_alias="ros", l3_technology_node_id=10),
            TechnologyPattern(alias_id=2, normalized_alias="ros2", l3_technology_node_id=11),
            TechnologyPattern(alias_id=3, normalized_alias="雷达", l3_technology_node_id=12),
            TechnologyPattern(alias_id=4, normalized_alias="激光雷达", l3_technology_node_id=13),
        ]
    )

    hits = matcher.find("使用ROS2和ROS，不匹配CROSS；使用激光雷达。")

    assert [(hit.alias_id, hit.matched_text) for hit in hits] == [
        (2, "ROS2"),
        (1, "ROS"),
        (4, "激光雷达"),
    ]
