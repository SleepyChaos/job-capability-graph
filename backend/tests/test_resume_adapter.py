import io

import pytest

from app.modules.talent.resume_adapter import (
    MAX_RESUME_BYTES,
    ResumeFileError,
    extract_resume_text,
    sniff_mime,
)

RESUME_TEXT = (
    "姓名：测试\n求职意向：机器人算法工程师\n"
    "负责SLAM与运动规划模块开发，熟悉C++与ROS2。"
)


def test_txt_extraction_utf8_and_gbk() -> None:
    text, mime, input_type = extract_resume_text(
        "resume.txt", RESUME_TEXT.encode("utf-8")
    )
    assert "机器人算法工程师" in text
    assert mime == "text/plain"
    assert input_type == "txt"
    gbk_text, _, _ = extract_resume_text("resume.txt", RESUME_TEXT.encode("gbk"))
    assert "机器人算法工程师" in gbk_text


def test_doc_is_quarantined() -> None:
    with pytest.raises(ResumeFileError, match="隔离"):
        extract_resume_text("old.doc", b"legacy binary content")


def test_unknown_extension_rejected() -> None:
    with pytest.raises(ResumeFileError, match="不支持的文件类型"):
        extract_resume_text("resume.exe", b"MZ...")


def test_pdf_magic_mismatch_rejected() -> None:
    with pytest.raises(ResumeFileError, match="不符"):
        extract_resume_text("fake.pdf", RESUME_TEXT.encode("utf-8"))


def test_size_limit() -> None:
    with pytest.raises(ResumeFileError, match="10MB"):
        extract_resume_text("big.txt", b"x" * (MAX_RESUME_BYTES + 1))


def test_sniff_mime() -> None:
    assert sniff_mime(b"%PDF-1.4 ...") == "application/pdf"
    assert sniff_mime(b"PK\x03\x04...").startswith("application/vnd.openxmlformats")
    assert sniff_mime(b"plain text") == "text/plain"


def test_docx_extraction() -> None:
    import docx

    document = docx.Document()
    for line in RESUME_TEXT.splitlines():
        document.add_paragraph(line)
    buffer = io.BytesIO()
    document.save(buffer)
    text, mime, input_type = extract_resume_text("resume.docx", buffer.getvalue())
    assert "机器人算法工程师" in text
    assert mime.startswith("application/vnd.openxmlformats")
    assert input_type == "docx_text"


def test_pdf_without_text_is_rejected() -> None:
    # 只有占位内容的极简 PDF：无可提取文本时应明确报错（OCR 未接入降级）
    pdf = (
        b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] >>\nendobj\n"
        b"trailer\n<< /Size 4 /Root 1 0 R >>\n%%EOF\n"
    )
    with pytest.raises(ResumeFileError):
        extract_resume_text("scan.pdf", pdf)


def test_virus_scan_placeholder() -> None:
    from app.modules.talent.resume_adapter import virus_scan

    result = virus_scan(b"data")
    assert result["status"] == "skipped"
    assert result["engine"] == "none"
