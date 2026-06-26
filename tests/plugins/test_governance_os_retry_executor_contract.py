"""Retry executor contract coverage for governed tool-result failures."""

from __future__ import annotations

import json

from plugins.governance_os.result_transform import governance_transform_tool_result


def test_retry_required_payload_contains_agentic_executor_contract() -> None:
    transformed = governance_transform_tool_result(
        tool_name="media_delivery_contract",
        args={"artifact_path": "/tmp/report.mhtml"},
        result=json.dumps({"success": True, "artifact_path": "/tmp/report.mhtml"}),
        tool_call_id="tool-call-1",
    )

    assert transformed is not None
    payload = json.loads(transformed)
    executor = payload["auto_retry_executor"]
    assert executor["status"] == "required"
    assert executor["mode"] == "agentic_tool_loop"
    assert executor["tool_call_id"] == "tool-call-1"
    assert executor["retry_tools"] == ["media_delivery_contract"]
    assert executor["retry_args"] == [{"artifact_path": "/tmp/report.mhtml"}]
    assert "후검증" not in executor["user_visible_summary"]
    assert "retry_tools" not in executor["user_visible_summary"]


def test_retry_executor_reruns_tool_until_reviewer_passes(monkeypatch) -> None:
    calls: list[tuple[str, dict[str, object]]] = []
    retry_result = {
        "success": True,
        "artifact_path": "/tmp/report.mhtml",
        "media_tag": "MEDIA:/tmp/report.mhtml",
        "reviewer": {
            "name": "attachment_delivery_review",
            "status": "pass",
            "checked": ["media_tag", "artifact_path"],
        },
    }

    def fake_dispatch(name: str, args: dict[str, object], **_kwargs: object) -> str:
        calls.append((name, args))
        return json.dumps(retry_result, ensure_ascii=False)

    monkeypatch.setattr("tools.registry.registry.dispatch", fake_dispatch)
    monkeypatch.setattr(
        "plugins.governance_os.review._call_auxiliary_reviewer",
        lambda **_kwargs: {
            "status": "pass",
            "checked": ["media_tag", "artifact_path"],
        },
    )

    transformed = governance_transform_tool_result(
        tool_name="media_delivery_contract",
        args={"artifact_path": "/tmp/report.mhtml"},
        result=json.dumps({"success": True, "artifact_path": "/tmp/report.mhtml"}),
        tool_call_id="tool-call-1",
        governance_skip_ledger=True,
    )

    assert transformed is not None
    payload = json.loads(transformed)
    assert payload["reviewer"]["status"] == "pass"
    assert calls == [("media_delivery_contract", {"artifact_path": "/tmp/report.mhtml"})]


def test_retry_executor_keeps_block_payload_when_retry_fails(monkeypatch) -> None:
    def fake_dispatch(*_args: object, **_kwargs: object) -> str:
        return json.dumps({"success": True, "artifact_path": "/tmp/report.mhtml"})

    monkeypatch.setattr("tools.registry.registry.dispatch", fake_dispatch)

    transformed = governance_transform_tool_result(
        tool_name="media_delivery_contract",
        args={"artifact_path": "/tmp/report.mhtml"},
        result=json.dumps({"success": True, "artifact_path": "/tmp/report.mhtml"}),
        tool_call_id="tool-call-1",
        governance_skip_ledger=True,
    )

    assert transformed is not None
    payload = json.loads(transformed)
    assert payload["next_action"] == "retry_required"
    attempts = payload["auto_retry_executor"]["attempts"]
    assert attempts
    assert attempts[0]["status"] == "fail"


def test_retry_executor_fail_closes_when_retry_dispatch_raises(monkeypatch) -> None:
    def broken_dispatch(*_args: object, **_kwargs: object) -> str:
        raise RuntimeError("tool down")

    monkeypatch.setattr("tools.registry.registry.dispatch", broken_dispatch)

    transformed = governance_transform_tool_result(
        tool_name="media_delivery_contract",
        args={"artifact_path": "/tmp/report.mhtml"},
        result=json.dumps({"success": True, "artifact_path": "/tmp/report.mhtml"}),
        tool_call_id="tool-call-1",
        governance_skip_ledger=True,
    )

    assert transformed is not None
    payload = json.loads(transformed)
    assert payload["next_action"] == "retry_required"
    attempts = payload["auto_retry_executor"]["attempts"]
    assert attempts[0]["status"] == "fail"
    assert attempts[0]["reason"] == "retry_dispatch_error:RuntimeError"


def test_retry_executor_feeds_vision_review_into_pdf_gate(monkeypatch) -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    def fake_dispatch(name: str, args: dict[str, object], **_kwargs: object) -> str:
        calls.append((name, args))
        if name == "vision_analyze":
            return json.dumps(
                {
                    "success": True,
                    "analysis": json.dumps(
                        {
                            "status": "pass",
                            "checked": ["footer_layout", "no_text_overlap"],
                            "summary": "전달 가능",
                        },
                        ensure_ascii=False,
                    ),
                },
                ensure_ascii=False,
            )
        if name == "html_pdf_quality_gate" and args.get("visual_review"):
            return json.dumps(
                {
                    "success": True,
                    "artifact_path": "/tmp/report.pdf",
                    "pdf_quality_gate": {"ok": True, "page_count": 1},
                    "reviewer": {
                        "name": "html_pdf_quality_review",
                        "status": "pass",
                        "checked": [
                            "html_source",
                            "pdf_rendered",
                            "metadata_scrubbed",
                            "contact_sheet",
                            "visual_review",
                        ],
                    },
                },
                ensure_ascii=False,
            )
        return json.dumps(
            {
                "success": False,
                "reviewer": {
                    "name": "html_pdf_quality_review",
                    "status": "retry_needed",
                    "checked": ["html_source", "pdf_rendered", "contact_sheet"],
                    "retry_tools": ["vision_analyze", "html_pdf_quality_gate"],
                },
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr("tools.registry.registry.dispatch", fake_dispatch)
    monkeypatch.setattr(
        "plugins.governance_os.review._call_auxiliary_reviewer",
        lambda **_kwargs: {
            "status": "pass",
            "checked": [
                "html_source",
                "pdf_rendered",
                "metadata_scrubbed",
                "contact_sheet",
                "visual_review",
            ],
        },
    )

    transformed = governance_transform_tool_result(
        tool_name="html_pdf_quality_gate",
        result=json.dumps(
            {
                "success": False,
                "artifact_path": "/tmp/report.pdf",
                "pdf_quality_gate": {"ok": True, "page_count": 1},
                "reviewer": {
                    "name": "html_pdf_quality_review",
                    "status": "retry_needed",
                    "checked": [
                        "html_source",
                        "pdf_rendered",
                        "metadata_scrubbed",
                        "page_previews",
                        "contact_sheet",
                    ],
                    "retry_tools": ["vision_analyze", "html_pdf_quality_gate"],
                    "retry_args": [
                        {"image_url": "/tmp/contact_sheet.png", "question": "검수"},
                        {"html_path": "/tmp/source.html", "pdf_path": "/tmp/report.pdf"},
                    ],
                },
            },
            ensure_ascii=False,
        ),
        governance_skip_ledger=True,
    )

    assert transformed is not None
    payload = json.loads(transformed)
    assert payload["reviewer"]["status"] == "pass"
    assert calls[0][0] == "vision_analyze"
    assert calls[1][0] == "html_pdf_quality_gate"
    assert calls[1][1]["visual_review"]["success"] is True


def test_retry_executor_autocorrects_rerenders_and_delivers_pdf(monkeypatch, tmp_path) -> None:
    calls: list[tuple[str, dict[str, object]]] = []
    source = tmp_path / "source.html"
    corrected = tmp_path / "source.autofixed.html"
    pdf = tmp_path / "report.pdf"
    sheet = tmp_path / "contact_sheet_fixed.png"
    source.write_text("<html><body><footer>맥스체대입시</footer></body></html>", encoding="utf-8")
    corrected.write_text("<html><body><footer>맥스체대입시</footer></body></html>", encoding="utf-8")
    pdf.write_bytes(b"%PDF-1.7 fake")
    sheet.write_bytes(b"png")

    def fake_dispatch(name: str, args: dict[str, object], **_kwargs: object) -> str:
        calls.append((name, args))
        if name == "html_pdf_autocorrect":
            return json.dumps(
                {
                    "success": True,
                    "html_path": str(corrected),
                    "artifact_path": str(corrected),
                    "reviewer": {
                        "name": "html_pdf_autocorrect_review",
                        "status": "pass",
                        "checked": ["print_css", "footer_guard", "overflow_guard"],
                    },
                },
                ensure_ascii=False,
            )
        if name == "html_pdf_quality_gate" and not args.get("visual_review"):
            return json.dumps(
                {
                    "success": False,
                    "artifact_path": str(pdf),
                    "contact_sheet_path": str(sheet),
                    "pdf_quality_gate": {
                        "ok": True,
                        "contact_sheet": str(sheet),
                        "review_prompt": "footer와 줄맞춤 검수",
                    },
                    "reviewer": {
                        "name": "html_pdf_quality_review",
                        "status": "retry_needed",
                        "checked": [
                            "html_source",
                            "pdf_rendered",
                            "metadata_scrubbed",
                            "page_previews",
                            "contact_sheet",
                        ],
                        "retry_tools": ["vision_analyze", "html_pdf_quality_gate"],
                    },
                },
                ensure_ascii=False,
            )
        if name == "vision_analyze":
            return json.dumps(
                {
                    "success": True,
                    "analysis": json.dumps(
                        {
                            "status": "pass",
                            "checked": [
                                "line_alignment",
                                "footer_layout",
                                "no_text_overlap",
                                "design_quality",
                            ],
                            "summary": "전달 가능",
                        },
                        ensure_ascii=False,
                    ),
                },
                ensure_ascii=False,
            )
        if name == "html_pdf_quality_gate" and args.get("visual_review"):
            return json.dumps(
                {
                    "success": True,
                    "artifact_path": str(pdf),
                    "pdf_path": str(pdf),
                    "contact_sheet_path": str(sheet),
                    "pdf_quality_gate": {"ok": True, "page_count": 1},
                    "reviewer": {
                        "name": "html_pdf_quality_review",
                        "status": "pass",
                        "checked": [
                            "html_source",
                            "pdf_rendered",
                            "metadata_scrubbed",
                            "page_previews",
                            "contact_sheet",
                            "visual_review",
                        ],
                    },
                },
                ensure_ascii=False,
            )
        if name == "media_delivery_contract":
            return json.dumps(
                {
                    "success": True,
                    "artifact_path": args["artifact_path"],
                    "media_tag": f"MEDIA:{args['artifact_path']}",
                    "delivery_text": f"완성본이야.\nMEDIA:{args['artifact_path']}",
                    "reviewer": {
                        "name": "attachment_delivery_review",
                        "status": "pass",
                        "checked": ["media_tag", "artifact_path"],
                        "evidence_required": True,
                    },
                },
                ensure_ascii=False,
            )
        raise AssertionError(f"unexpected tool call: {name} {args}")

    monkeypatch.setattr("tools.registry.registry.dispatch", fake_dispatch)
    monkeypatch.setattr(
        "plugins.governance_os.review._call_auxiliary_reviewer",
        lambda **_kwargs: {
            "status": "pass",
            "checked": [
                "html_source",
                "pdf_rendered",
                "metadata_scrubbed",
                "contact_sheet",
                "visual_review",
                "media_tag",
                "artifact_path",
            ],
        },
    )

    transformed = governance_transform_tool_result(
        tool_name="html_pdf_quality_gate",
        result=json.dumps(
            {
                "success": False,
                "artifact_path": str(pdf),
                "pdf_quality_gate": {"ok": True, "page_count": 1},
                "visual_review": {
                    "status": "fail",
                    "errors": ["footer가 페이지 밖으로 밀림", "줄 정렬 불량"],
                },
                "reviewer": {
                    "name": "html_pdf_quality_review",
                    "status": "retry_needed",
                    "checked": [
                        "html_source",
                        "pdf_rendered",
                        "metadata_scrubbed",
                        "page_previews",
                        "contact_sheet",
                        "visual_review",
                    ],
                    "retry_tools": [
                        "html_pdf_autocorrect",
                        "html_pdf_quality_gate",
                        "vision_analyze",
                        "html_pdf_quality_gate",
                        "media_delivery_contract",
                    ],
                    "retry_args": [
                        {
                            "html_path": str(source),
                            "visual_review": {
                                "status": "fail",
                                "errors": ["footer가 페이지 밖으로 밀림"],
                            },
                        },
                        {"html_path": str(source), "pdf_path": str(pdf)},
                        {"question": "footer와 줄맞춤 검수"},
                        {"html_path": str(source), "pdf_path": str(pdf)},
                        {"caption": "완성본이야."},
                    ],
                },
            },
            ensure_ascii=False,
        ),
        governance_skip_ledger=True,
    )

    assert transformed is not None
    payload = json.loads(transformed)
    assert payload["success"] is True
    assert payload["media_tag"] == f"MEDIA:{pdf}"
    assert [name for name, _args in calls] == [
        "html_pdf_autocorrect",
        "html_pdf_quality_gate",
        "vision_analyze",
        "html_pdf_quality_gate",
        "media_delivery_contract",
    ]
    assert calls[1][1]["html_path"] == str(corrected)
    assert calls[2][1]["image_url"] == str(sheet)
    assert calls[3][1]["visual_review"]["success"] is True
    assert calls[4][1]["artifact_path"] == str(pdf)
