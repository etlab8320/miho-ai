"""Fast-path tests for text-layer life-record PDFs."""

from __future__ import annotations

import json
from types import SimpleNamespace

from gateway.config import Platform
from gateway.platforms.base import MessageEvent
from gateway.session import SessionSource
from plugins.life_record.context import capture_gateway_context


def _event(thread_id: str) -> MessageEvent:
    return MessageEvent(
        text="생기부 PDF 넣어줘",
        source=SessionSource(
            platform=Platform.DISCORD,
            user_id="discord-user-1",
            chat_id=thread_id,
            parent_chat_id="channel-1",
            guild_id="guild-1",
        ),
    )


def _sample_pdf_text() -> str:
    return """
학교생활세부사항기록부(학교생활기록부II)
학년
반
번호
담임성명
1
3
5
김교사
1. 인적·학적사항
성명 : 홍길동
주민등록번호 : 070101-*******
2024년 3월 2일 서울고등학교 제1학년 입학
2. 출 결 상 황
학년
수업일수
1
190
.
.
.
.
.
.
.
.
.
.
.
개근
3. 수 상 경 력
학년
수상명
수상연월일
수여기관
1
모범상
2024.07.19.
서울고등학교장
6. 교과학습발달상황
[1학년]
학기
1
교과
과목
학점수
원점수/과목평균
(표준편차)
성취도
(수강자수)
석차등급
국어
국어
4
90/70.0(10.0)
A(200)
2
과목
세부능력및특기사항
(1학기)국어: 발표와 토론에서 논리적으로 의견을 제시하고 근거를 들어 설명함.
8. 행동특성 및 종합의견
행동특성및종합의견
1
책임감 있게 학급 활동에 참여함.
"""


def test_text_layer_pdf_does_not_wait_for_life_record_text_model(monkeypatch, tmp_path) -> None:
    import plugins.life_record.service as service_module
    import plugins.life_record.vision_extractor as vision_module
    from plugins.life_record.tools import _ingest_pdf_tool_handler

    monkeypatch.setenv("MIHO_HOME", str(tmp_path))
    monkeypatch.delenv("MIHO_LIFE_RECORD_TEXT_MODEL_PASS", raising=False)
    monkeypatch.setattr(
        service_module,
        "extract_pdf",
        lambda _p: SimpleNamespace(
            page_texts=[_sample_pdf_text()],
            raw_text=_sample_pdf_text(),
            page_count=1,
            metadata={},
            photo=None,
        ),
    )
    monkeypatch.setattr(service_module, "render_page_images", lambda *a, **k: [b"\x89PNG\r\n\x1a\n"])

    async def _model_must_not_run(_prompt):
        raise AssertionError("text-layer PDF must not call life_record_text by default")

    async def _vision_must_not_run(_images, _prompt):
        raise AssertionError("text-layer PDF must not call vision extraction")

    monkeypatch.setattr(vision_module, "default_text_resolver", _model_must_not_run)
    monkeypatch.setattr(vision_module, "default_codex_resolver", _vision_must_not_run)

    pdf = tmp_path / "record.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    capture_gateway_context(_event("thread-text-pdf"))
    result = json.loads(_ingest_pdf_tool_handler({"pdf_path": str(pdf)}))

    assert result["ok"] is True
    assert result["student"]["name"] == "홍길동"
    assert result["runs"] == 2
    assert result["counts"]["subject_grade_rows"] == 1
    assert result["counts"]["special_note_rows"] >= 1
