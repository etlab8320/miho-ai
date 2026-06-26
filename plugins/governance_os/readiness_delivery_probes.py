"""Final Delivery readiness probes for Governance OS."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import cast

from .registry import GovernanceRegistry


def final_delivery_probe_passed(registry: GovernanceRegistry) -> bool:
    from .delivery_gate import evaluate_final_delivery, governance_transform_llm_output

    def fake_call_llm(*_args: object, **_kwargs: object) -> dict[str, object]:
        return {
            "content": (
                '{"action":"revise","answer":"서연이 수시 환산점수는 확정 산출 불가입니다.\\n'
                '필요한 입력: 학생 성적, 지원 대학, 전형, 실기 기록."}'
            )
        }

    def extract(response: object) -> str:
        if isinstance(response, dict):
            typed = cast("dict[str, object]", response)
            return str(typed.get("content") or "")
        return str(response or "")

    def recovery_call_llm(*_args: object, **kwargs: object) -> dict[str, object]:
        task = str(kwargs.get("task") or "")
        if task == "miho_governance_final_delivery":
            return {"content": "not-json"}
        if task == "miho_governance_final_qa_repair":
            return {"content": "서연이 수시 환산점수는 947.3점입니다."}
        if task == "miho_governance_final_qa":
            return {"content": "pass"}
        if task == "miho_governance_blocked_delivery_recovery":
            return {"content": "확정 환산점수 산출 불가.\n필요한 입력: 학생 성적, 지원 대학, 전형, 실기 기록."}
        return {"content": ""}

    blocked = evaluate_final_delivery(
        registry,
        response_text="서연이 수시 환산점수는 947.3점입니다.",
        user_text="서연이 수시 환산점수 계산해줘",
        outcomes=[],
    )
    passed = evaluate_final_delivery(
        registry,
        response_text="서연이 수시 환산점수는 947.3점입니다.",
        user_text="서연이 수시 환산점수 계산해줘",
        outcomes=[
            {
                "playbook_key": "susi_score_calculation",
                "review_status": "pass",
                "tools_used": ["susi27_score_calculate"],
                "failures": [],
            }
        ],
    )
    transformed = governance_transform_llm_output(
        response_text="서연이 수시 환산점수는 947.3점입니다.",
        user_message="서연이 수시 환산점수 계산해줘",
        governance_outcomes=[],
        final_delivery_call_llm=fake_call_llm,
        final_delivery_extract_content=extract,
    )
    recovered = governance_transform_llm_output(
        response_text="서연이 수시 환산점수는 947.3점입니다.",
        user_message="서연이 수시 환산점수 계산해줘",
        governance_outcomes=[],
        final_delivery_call_llm=recovery_call_llm,
        final_delivery_extract_content=extract,
    )
    return (
        blocked.action == "block"
        and blocked.reason == "review_evidence_missing"
        and passed.action == "allow"
        and transformed is not None
        and "확정 산출 불가" in transformed
        and recovered is not None
        and "947.3" not in recovered
        and "확정 환산점수 산출 불가" in recovered
        and "확인된 뒤" not in transformed
        and "확인한 뒤" not in recovered
        and "후검증" not in transformed
        and "전용 도구" not in transformed
    )


def final_delivery_retry_probe_passed(registry: GovernanceRegistry) -> bool:
    import plugins.governance_os.review as review_module

    from .final_delivery_orchestrator import FINAL_DELIVERY_ORCHESTRATOR_TASK
    from .final_delivery_retry import retry_blocked_final_delivery

    temp_dir = tempfile.TemporaryDirectory()
    artifact_path = Path(temp_dir.name) / "report.mhtml"
    artifact_path.write_text("<html><body>첨부 검수본</body></html>", encoding="utf-8")

    def fake_dispatch(*_args: object, **_kwargs: object) -> str:
        return json.dumps(
            {
                "success": True,
                "artifact_path": str(artifact_path),
                "media_tag": f"MEDIA:{artifact_path}",
                "reviewer": {
                    "name": "attachment_delivery_review",
                    "status": "pass",
                    "checked": ["media_tag", "artifact_path"],
                    "evidence_required": True,
                },
            },
            ensure_ascii=False,
        )

    def fake_auxiliary_reviewer(**_kwargs: object) -> dict[str, object]:
        return {"status": "pass", "checked": ["media_tag", "artifact_path"]}

    orchestrator_calls: list[dict[str, object]] = []
    orchestrator_modes: list[str] = []

    def fake_orchestrator_llm(*_args: object, **kwargs: object) -> dict[str, object]:
        orchestrator_calls.append(kwargs)
        messages = kwargs.get("messages")
        if not isinstance(messages, list):
            return {"content": ""}
        prompt = str(messages[1]["content"])
        payload = json.loads(prompt)
        mode = str(payload.get("mode") or "")
        orchestrator_modes.append(mode)
        if mode == "compose_answer":
            return {
                "content": json.dumps(
                    {
                        "action": "deliver",
                        "answer": f"완성본이야.\nMEDIA:{artifact_path}",
                        "reason": "verified media result passed review",
                    },
                    ensure_ascii=False,
                )
            }
        return {
            "content": json.dumps(
                {
                    "action": "run_tools",
                    "steps": [
                        {
                            "tool_name": "media_delivery_contract",
                            "args": {"artifact_path": str(artifact_path)},
                        }
                    ],
                    "reason": "readiness probe",
                },
                ensure_ascii=False,
            )
        }

    def extract(response: object) -> str:
        if isinstance(response, dict):
            typed = cast("dict[str, object]", response)
            return str(typed.get("content") or "")
        return str(response or "")

    original = review_module._call_auxiliary_reviewer
    review_module._call_auxiliary_reviewer = fake_auxiliary_reviewer
    try:
        direct_result = retry_blocked_final_delivery(
            registry=registry,
            playbook_key="discord_attachment_delivery",
            retry_tools=("media_delivery_contract",),
            question="mhtml 파일 첨부해서 보내줘",
            conversation_history=[
                {"role": "user", "content": "mhtml 파일 첨부해서 보내줘"},
                {
                    "role": "tool",
                    "name": "media_delivery_contract",
                    "content": json.dumps(
                        {
                            "success": False,
                            "governance_review": {
                                "retry_args": [{"artifact_path": str(artifact_path)}]
                            },
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            dispatch_tool=fake_dispatch,
        )
        orchestrated_result = retry_blocked_final_delivery(
            registry=registry,
            playbook_key="discord_attachment_delivery",
            retry_tools=("media_delivery_contract",),
            question="mhtml 파일 첨부해서 보내줘",
            answer="MHTML 파일을 첨부했습니다.",
            conversation_history=[
                {"role": "user", "content": "mhtml 파일 첨부해서 보내줘"},
            ],
            dispatch_tool=fake_dispatch,
            orchestrator_call_llm=fake_orchestrator_llm,
            orchestrator_extract_content=extract,
        )
    finally:
        review_module._call_auxiliary_reviewer = original
        temp_dir.cleanup()
    return (
        direct_result is not None
        and direct_result.tool_name == "media_delivery_contract"
        and f"MEDIA:{artifact_path}" in direct_result.answer
        and direct_result.review_reason == "auxiliary_reviewer_pass"
        and orchestrated_result is not None
        and orchestrated_result.tool_name == "media_delivery_contract"
        and f"MEDIA:{artifact_path}" in orchestrated_result.answer
        and orchestrated_result.review_reason == "auxiliary_reviewer_pass"
        and orchestrated_result.answer_source == "orchestrator_agent"
        and orchestrator_modes == ["plan_tools", "compose_answer"]
        and bool(orchestrator_calls)
        and orchestrator_calls[0].get("task") == FINAL_DELIVERY_ORCHESTRATOR_TASK
    )


def pdf_attachment_quality_loop_probe_passed(registry: GovernanceRegistry) -> bool:
    import plugins.governance_os.review as review_module

    from .result_transform import governance_transform_tool_result
    from tools.html_pdf_autocorrect_tool import html_pdf_autocorrect_tool
    from tools.html_pdf_quality_gate_tool import html_pdf_quality_gate_tool

    if "designed_pdf_artifact" not in registry.playbooks:
        return False

    temp_dir = tempfile.TemporaryDirectory()
    base = Path(temp_dir.name)
    source = base / "source.html"
    corrected = base / "source.autofixed.html"
    pdf_path = base / "report.pdf"
    source.write_text(
        (
            "<!doctype html><html lang='ko'><head><meta charset='utf-8'>"
            "<style>@page{size:A4;margin:18mm 16mm 20mm}"
            "body{font-family:Arial,sans-serif;line-height:1.55;color:#111}"
            "h1{font-size:24px}p{font-size:13px}footer{margin-top:24px;font-size:10px}"
            "</style></head><body><h1>4개월 시즌 운동 프로그램</h1>"
            "<p>고강도 훈련은 목적에 맞춰 배치하고 회복일과 기록 측정일을 분리한다.</p>"
            "<p>월수목금토 기준으로 오후 훈련과 야간 훈련을 나누어 운영한다.</p>"
            "<footer>맥스체대입시 상담자료</footer></body></html>"
        ),
        encoding="utf-8",
    )
    calls: list[tuple[str, dict[str, object]]] = []

    def fake_dispatch(name: str, args: dict[str, object], **_kwargs: object) -> str:
        calls.append((name, args))
        if name == "html_pdf_autocorrect":
            return html_pdf_autocorrect_tool(args)
        if name == "html_pdf_quality_gate" and not args.get("visual_review"):
            return html_pdf_quality_gate_tool(
                {**args, "engine": "playwright", "timeout": 60}
            )
        if name == "vision_analyze":
            return json.dumps(
                {
                    "success": True,
                    "analysis": json.dumps(
                        {
                            "status": "pass",
                            "checked": ["line_alignment", "footer_layout", "no_text_overlap"],
                        },
                        ensure_ascii=False,
                    ),
                },
                ensure_ascii=False,
            )
        if name == "html_pdf_quality_gate" and args.get("visual_review"):
            return html_pdf_quality_gate_tool(
                {**args, "engine": "playwright", "timeout": 60}
            )
        if name == "media_delivery_contract":
            return json.dumps(
                {
                    "success": True,
                    "artifact_path": args.get("artifact_path"),
                    "media_tag": f"MEDIA:{args.get('artifact_path')}",
                    "delivery_text": f"완성본이야.\nMEDIA:{args.get('artifact_path')}",
                    "reviewer": {
                        "name": "attachment_delivery_review",
                        "status": "pass",
                        "checked": ["media_tag", "artifact_path"],
                        "evidence_required": True,
                    },
                },
                ensure_ascii=False,
            )
        return json.dumps({"success": False}, ensure_ascii=False)

    def fake_auxiliary_reviewer(**_kwargs: object) -> dict[str, object]:
        return {
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
        }

    from tools.registry import registry as tool_registry

    original_dispatch = tool_registry.dispatch
    original_reviewer = review_module._call_auxiliary_reviewer
    tool_registry.dispatch = fake_dispatch  # type: ignore[method-assign]
    review_module._call_auxiliary_reviewer = fake_auxiliary_reviewer
    passed = False
    try:
        transformed = governance_transform_tool_result(
            tool_name="html_pdf_quality_gate",
            result=json.dumps(
                {
                    "success": False,
                    "artifact_path": str(pdf_path),
                    "visual_review": {
                        "status": "fail",
                        "errors": ["footer가 페이지 밖으로 밀림"],
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
                            {"html_path": str(source), "visual_review": {"status": "fail"}},
                            {"html_path": str(source), "pdf_path": str(pdf_path)},
                            {"question": "footer와 줄맞춤 검수"},
                            {"html_path": str(source), "pdf_path": str(pdf_path)},
                            {"caption": "완성본이야."},
                        ],
                    },
                },
                ensure_ascii=False,
            ),
            governance_skip_ledger=True,
        )
        passed = (
            bool(transformed)
            and json.loads(str(transformed))["media_tag"] == f"MEDIA:{pdf_path.resolve()}"
            and [name for name, _args in calls]
            == [
                "html_pdf_autocorrect",
                "html_pdf_quality_gate",
                "vision_analyze",
                "html_pdf_quality_gate",
                "media_delivery_contract",
            ]
            and Path(str(calls[1][1].get("html_path") or "")).resolve()
            == corrected.resolve()
            and Path(str(calls[2][1].get("image_url") or "")).is_file()
            and calls[3][1].get("visual_review") is not None
            and calls[4][1].get("artifact_path") == str(pdf_path.resolve())
        )
    finally:
        tool_registry.dispatch = original_dispatch  # type: ignore[method-assign]
        review_module._call_auxiliary_reviewer = original_reviewer
        temp_dir.cleanup()
    return passed
