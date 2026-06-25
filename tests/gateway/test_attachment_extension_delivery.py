"""Attachment extension coverage for gateway media extraction."""

from gateway.platforms.base import BasePlatformAdapter


def test_media_tag_supports_unquoted_web_archives_and_korean_office_documents():
    content = "\n".join(
        [
            "자료 만들었어.",
            "MEDIA:/tmp/miho/서연_학종_리포트.mhtml",
            "MEDIA:/tmp/miho/생기부_원본.hwpx",
        ]
    )

    media, cleaned = BasePlatformAdapter.extract_media(content)

    assert media == [
        ("/tmp/miho/서연_학종_리포트.mhtml", False),
        ("/tmp/miho/생기부_원본.hwpx", False),
    ]
    assert "자료 만들었어." in cleaned
    assert "MEDIA:" not in cleaned


def test_extract_local_files_supports_web_archives_and_korean_office_documents(tmp_path):
    files = [
        tmp_path / "상담기록.hwp",
        tmp_path / "학종리포트.hwpx",
        tmp_path / "입시자료.mhtml",
        tmp_path / "저장본.mht",
        tmp_path / "성적표.numbers",
    ]
    for path in files:
        path.write_bytes(b"artifact")
    content = "첨부 경로:\n" + "\n".join(str(path) for path in files)

    extracted, cleaned = BasePlatformAdapter.extract_local_files(content)

    assert extracted == [str(path) for path in files]
    for path in files:
        assert str(path) not in cleaned
    assert "첨부 경로:" in cleaned
