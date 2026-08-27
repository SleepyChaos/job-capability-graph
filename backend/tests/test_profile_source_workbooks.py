from pathlib import Path

from openpyxl import Workbook

from tools.profile_source_workbooks import run


def test_profile_workbook_omits_cell_values_and_counts_duplicates(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    restricted_dir = source_root / "restricted"
    restricted_dir.mkdir(parents=True)
    workbook_path = restricted_dir / "demo.xlsx"

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "岗位"
    sheet.append(["姓名", "技术词"])
    sheet.append(["张三", "ROS 2"])
    sheet.append(["张三", "ROS 2"])
    workbook.save(workbook_path)

    output_dir = tmp_path / "report"
    profiles = run(source_root, output_dir)

    assert len(profiles) == 1
    assert profiles[0].access_classification == "restricted"
    assert profiles[0].sheets[0].duplicate_data_row_count == 1
    report = (output_dir / "xlsx_profile.md").read_text(encoding="utf-8")
    assert "姓名" in report
    assert "张三" not in report
