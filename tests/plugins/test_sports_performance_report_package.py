"""Tests for the sports motion report package tool."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from plugins import sports_performance
from plugins.sports_performance import feedback_tool, max_analysis_api, report_package
from plugins.sports_performance.report_package import build_sports_motion_report_package


def _row(**overrides: Any) -> dict[str, Any]:
    row = {
        "student_name": "강지연",
        "academy_name": "맥스체대입시_일산 교육원",
        "measured_at": "2026-06-27",
        "sport": "SLJ",
        "session_id": "session-new",
        "record_value": 218.0,
        "record_unit": "cm",
        "phase": "takeoff",
        "variable_key": "takeoff_angle",
        "variable_name": "뛰어오르는 각도",
        "variable_value": 22.4,
        "unit": "deg",
    }
    row.update(overrides)
    return row


class _Ctx:
    def __init__(self) -> None:
        self.tools: list[str] = []

    def register_tool(self, *, name: str, **_: Any) -> None:
        self.tools.append(name)

    def register_hook(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def register_auxiliary_task(self, *_args: Any, **_kwargs: Any) -> None:
        return None


def test_report_package_tool_is_registered_with_plugin_yaml() -> None:
    ctx = _Ctx()

    sports_performance.register(ctx)

    yaml_text = Path("plugins/sports_performance/plugin.yaml").read_text(encoding="utf-8")
    assert "sports_motion_report_package" in ctx.tools
    assert "sports_motion_report_package" in yaml_text


def test_report_package_builds_pdf_contract_from_max_api(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("MAX_ANALYSIS_VARIABLES_API_KEY", "secret-key")
    monkeypatch.setenv("MIHO_HOME", str(tmp_path / "miho_home"))

    def fake_get_json(endpoint: str, *, params: dict[str, Any], api_key: str, timeout: int) -> list[dict[str, Any]]:
        del endpoint, params, api_key, timeout
        return [
            _row(variable_key="takeoff_angle", variable_value=22.4, unit="deg"),
            _row(variable_key="horizontal_velocity", variable_name="앞으로 나가는 속도", variable_value=4.18, unit="m/s"),
            _row(variable_key="vertical_velocity", variable_name="위로 뜨는 힘", variable_value=2.1, unit="m/s"),
            _row(student_name="상위학생", gender="female", session_id="elite", record_value=260.0, variable_key="takeoff_angle", variable_value=24.5, unit="deg"),
            _row(student_name="상위학생", gender="female", session_id="elite", record_value=260.0, variable_key="horizontal_velocity", variable_name="앞으로 나가는 속도", variable_value=4.9, unit="m/s"),
            _row(student_name="상위학생", gender="female", session_id="elite", record_value=260.0, variable_key="vertical_velocity", variable_name="위로 뜨는 힘", variable_value=2.5, unit="m/s"),
        ]

    def fake_pdf_gate(args: dict[str, Any]) -> dict[str, Any]:
        html_path = Path(args["html_path"])
        assert html_path.exists()
        html_text = html_path.read_text(encoding="utf-8")
        assert "22.40 deg" in html_text
        assert "24.50 deg" in html_text
        pdf_path = html_path.with_suffix(".pdf")
        pdf_path.write_bytes(b"%PDF-1.4\n% sports smoke\n")
        return {
            "success": True,
            "ok": True,
            "pdf_path": str(pdf_path),
            "artifact_path": str(pdf_path),
            "reviewer": {
                "name": "html_pdf_quality_review",
                "status": "pass",
                "checked": ["html_source", "pdf_rendered", "metadata_scrubbed", "contact_sheet", "visual_review"],
            },
        }

    monkeypatch.setattr(max_analysis_api, "_http_get_json", fake_get_json)
    monkeypatch.setattr(
        report_package,
        "build_pe_brain_evidence_response",
        lambda _args: {"ok": True, "packs": [{"id": "sports_ref:slj-local", "quality_status": "accepted"}]},
    )
    monkeypatch.setattr(
        feedback_tool,
        "resolve_pe_brain_evidence_refs",
        lambda refs, exercise_key: {
            "accepted_refs": list(refs),
            "invalid_refs": [],
            "accepted_packs": [{"id": ref, "quality_status": "accepted"} for ref in refs],
            "exercise_key": exercise_key,
        },
    )

    result = build_sports_motion_report_package(
        {"student_name": "강지연", "exercise": "제멀"},
        pdf_gate=fake_pdf_gate,
    )

    assert result["ok"] is True
    assert result["reviewer"]["status"] == "pass"
    assert result["feedback"]["reviewer"]["status"] == "pass"
    assert result["max_analysis"]["record_count"] == 3
    assert result["cohort_model"]["ok"] is True
    assert result["artifact_path"].endswith(".pdf")
    assert result["media_tag"].startswith("MEDIA:`")
    assert len(json.dumps(result, ensure_ascii=False)) < 8000
    assert "records" not in result["max_analysis"]
    assert "page_images" not in json.dumps(result, ensure_ascii=False)
    assert "측정 기록" not in result["delivery_text"]
    assert "필요합니다" not in result["delivery_text"]


def test_report_package_blocks_pdf_when_elite_model_is_missing(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("MAX_ANALYSIS_VARIABLES_API_KEY", "secret-key")
    monkeypatch.setenv("MIHO_HOME", str(tmp_path / "miho_home"))

    def fake_get_json(endpoint: str, *, params: dict[str, Any], api_key: str, timeout: int) -> list[dict[str, Any]]:
        del endpoint, params, api_key, timeout
        return [
            _row(student_name="강지연", variable_key="takeoff_angle", variable_value=22.4, unit="deg"),
            _row(student_name="강지연", variable_key="horizontal_velocity", variable_value=4.18, unit="m/s"),
        ]

    def fail_pdf_gate(_args: dict[str, Any]) -> dict[str, Any]:
        raise AssertionError("상위 1% 모델이 없으면 PDF 게이트를 호출하면 안 된다.")

    monkeypatch.setattr(max_analysis_api, "_http_get_json", fake_get_json)

    result = build_sports_motion_report_package(
        {"student_name": "강지연", "exercise": "제멀"},
        pdf_gate=fail_pdf_gate,
    )

    assert result["ok"] is False
    assert "상위 1% 모델" in " ".join(result["errors"])
    assert "pdf" not in result
    assert "MEDIA:" not in str(result)


def test_report_package_blocks_pdf_when_html_keeps_unlinked_model_text(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("MAX_ANALYSIS_VARIABLES_API_KEY", "secret-key")
    monkeypatch.setenv("MIHO_HOME", str(tmp_path / "miho_home"))

    rows = [
        _row(variable_key="takeoff_angle", variable_value=22.4, unit="deg"),
        _row(student_name="상위학생", gender="female", session_id="elite", record_value=260.0, variable_key="takeoff_angle", variable_value=24.5, unit="deg"),
    ]

    def fake_get_json(endpoint: str, *, params: dict[str, Any], api_key: str, timeout: int) -> list[dict[str, Any]]:
        del endpoint, params, api_key, timeout
        return rows

    def fake_write_html(_args: dict[str, Any]) -> dict[str, Any]:
        html_path = tmp_path / "bad_sports_report.html"
        html_path.write_text("전국 성별 상위 1% 모델 미연동", encoding="utf-8")
        return {"ok": True, "html_path": str(html_path), "template_key": "standing_long_jump_motion_report_v1"}

    def fail_pdf_gate(_args: dict[str, Any]) -> dict[str, Any]:
        raise AssertionError("상위 모델 미연동 HTML은 PDF 게이트로 넘기면 안 된다.")

    monkeypatch.setattr(max_analysis_api, "_http_get_json", fake_get_json)
    monkeypatch.setattr(report_package, "write_sports_report_html", fake_write_html)
    monkeypatch.setattr(
        report_package,
        "build_pe_brain_evidence_response",
        lambda _args: {"ok": True, "packs": [{"id": "sports_ref:slj-local", "quality_status": "accepted"}]},
    )
    monkeypatch.setattr(
        feedback_tool,
        "resolve_pe_brain_evidence_refs",
        lambda refs, exercise_key: {
            "accepted_refs": list(refs),
            "invalid_refs": [],
            "accepted_packs": [{"id": ref, "quality_status": "accepted"} for ref in refs],
            "exercise_key": exercise_key,
        },
    )

    result = build_sports_motion_report_package({"student_name": "강지연", "exercise": "제멀"}, pdf_gate=fail_pdf_gate)

    assert result["ok"] is False
    assert "상위 1%" in " ".join(result["errors"])
    assert "pdf" not in result
    assert "MEDIA:" not in str(result)


def test_report_package_pdf_gate_uses_deterministic_visual_pass(tmp_path) -> None:
    html_path = tmp_path / "sports_report.html"
    html_path.write_text("<html><body>상위 1% 24.50 deg</body></html>", encoding="utf-8")
    pdf_path = tmp_path / "sports_report.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n% sports smoke\n")
    calls: list[dict[str, Any]] = []

    class FailingLlm:
        def complete_structured(self, **_: Any) -> object:
            raise AssertionError("PDF layout pass should not depend on semantic LLM review.")

    def fake_pdf_gate(args: dict[str, Any]) -> dict[str, Any]:
        calls.append(dict(args))
        if len(calls) == 1:
            return {
                "success": False,
                "next_action": "visual_review_required",
                "html_path": str(html_path),
                "pdf_path": str(pdf_path),
                "artifact_path": str(pdf_path),
                "contact_sheet_path": str(tmp_path / "contact.png"),
                "page_images": [str(tmp_path / "page-1.png")],
                "pdf_quality_gate": {"layout_errors": [], "page_count": 4},
            }
        assert args["visual_review"]["status"] == "pass"
        assert "deterministic_pdf_layout_contract" in args["visual_review"]["checked"]
        return {"success": True, "ok": True, "pdf_path": str(pdf_path), "artifact_path": str(pdf_path)}

    result = report_package._run_pdf_gate(str(html_path), llm=FailingLlm(), pdf_gate=fake_pdf_gate)

    assert result["success"] is True
    assert len(calls) == 2


def test_report_package_real_pdf_gate_accepts_compact_prescription_page(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("MAX_ANALYSIS_VARIABLES_API_KEY", "secret-key")
    monkeypatch.setenv("MIHO_HOME", str(tmp_path / "miho_home"))

    def fake_get_json(endpoint: str, *, params: dict[str, Any], api_key: str, timeout: int) -> list[dict[str, Any]]:
        del endpoint, params, api_key, timeout
        return [
            _row(student_name="백종환", variable_key="takeoff_angle", variable_value=7.87, unit="deg"),
            _row(student_name="백종환", variable_key="horizontal_velocity", variable_value=0.76, unit="m/s"),
            _row(student_name="백종환", variable_key="vertical_velocity", variable_value=-0.22, unit="m/s"),
            _row(student_name="백종환", variable_key="takeoff_transition_time", variable_value=0.21, unit="s"),
            _row(student_name="상위학생", gender="male", session_id="elite", record_value=300.0, variable_key="takeoff_angle", variable_value=11.66, unit="deg"),
            _row(student_name="상위학생", gender="male", session_id="elite", record_value=300.0, variable_key="horizontal_velocity", variable_value=0.98, unit="m/s"),
            _row(student_name="상위학생", gender="male", session_id="elite", record_value=300.0, variable_key="vertical_velocity", variable_value=0.22, unit="m/s"),
            _row(student_name="상위학생", gender="male", session_id="elite", record_value=300.0, variable_key="takeoff_transition_time", variable_value=0.18, unit="s"),
        ]

    monkeypatch.setattr(max_analysis_api, "_http_get_json", fake_get_json)
    monkeypatch.setattr(
        report_package,
        "build_pe_brain_evidence_response",
        lambda _args: {"ok": True, "packs": [{"id": "sports_ref:slj-local", "quality_status": "accepted"}]},
    )
    monkeypatch.setattr(
        feedback_tool,
        "resolve_pe_brain_evidence_refs",
        lambda refs, exercise_key: {
            "accepted_refs": list(refs),
            "invalid_refs": [],
            "accepted_packs": [{"id": ref, "quality_status": "accepted"} for ref in refs],
            "exercise_key": exercise_key,
        },
    )

    result = build_sports_motion_report_package({"student_name": "백종환", "exercise": "제멀"})

    assert result["ok"] is True
    assert result["pdf"]["pdf_quality_gate"]["layout_errors"] == []
    assert result["reviewer"]["status"] == "pass"


def test_report_package_writes_record_change_and_real_top_five_model(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("MAX_ANALYSIS_VARIABLES_API_KEY", "secret-key")
    monkeypatch.setenv("MIHO_HOME", str(tmp_path / "miho_home"))

    rows = [
        _row(student_name="백종환", gender="male", measured_at="2026-03-31", session_id="latest", record_value=254.0, variable_key="takeoff_angle", variable_value=7.87, unit="°"),
        _row(student_name="백종환", gender="male", measured_at="2026-03-31", session_id="latest", record_value=254.0, variable_key="horizontal_velocity", variable_value=5.48, unit="m/s"),
        _row(student_name="백종환", gender="male", measured_at="2026-03-31", session_id="latest", record_value=254.0, variable_key="takeoff_transition_time", variable_value=0.17, unit="s"),
        _row(student_name="백종환", gender="male", measured_at="2026-03-07", session_id="previous", record_value=257.0, variable_key="takeoff_angle", variable_value=8.31, unit="°"),
        _row(student_name="상위학생", gender="male", measured_at="2026-03-31", session_id="elite", record_value=300.0, variable_key="takeoff_angle", variable_value=11.66, unit="°"),
        _row(student_name="상위학생", gender="male", measured_at="2026-03-31", session_id="elite", record_value=300.0, variable_key="horizontal_velocity", variable_value=4.76, unit="m/s"),
        _row(student_name="상위학생", gender="male", measured_at="2026-03-31", session_id="elite", record_value=300.0, variable_key="takeoff_transition_time", variable_value=0.33, unit="s"),
    ]

    def fake_get_json(endpoint: str, *, params: dict[str, Any], api_key: str, timeout: int) -> list[dict[str, Any]]:
        del endpoint, params, api_key, timeout
        return rows

    def fake_pdf_gate(args: dict[str, Any]) -> dict[str, Any]:
        html_path = Path(args["html_path"])
        html_text = html_path.read_text(encoding="utf-8")
        assert "2026-03-31 254cm" in html_text
        assert "-3cm" in html_text
        assert "변화량 미산출" not in html_text
        assert "다음 단계 계산 예정" not in html_text
        assert "HTML-first 템플릿" not in html_text
        assert "실제 API 조회값 연결 시 표시" not in html_text
        assert "github.com/shadcn-ui" not in html_text
        assert "상위 1% 대비 강점 변인" in html_text
        assert "강점 변인 3개" not in html_text
        assert "전국 상위 1%" in html_text
        assert "차이 +0.72 m/s" in html_text
        assert "앞으로 나가는 속도" in html_text
        pdf_path = html_path.with_suffix(".pdf")
        pdf_path.write_bytes(b"%PDF-1.4\n% sports smoke\n")
        return {"success": True, "ok": True, "pdf_path": str(pdf_path), "artifact_path": str(pdf_path)}

    monkeypatch.setattr(max_analysis_api, "_http_get_json", fake_get_json)
    monkeypatch.setattr(
        report_package,
        "build_pe_brain_evidence_response",
        lambda _args: {"ok": True, "packs": [{"id": "sports_ref:slj-local", "quality_status": "accepted"}]},
    )
    monkeypatch.setattr(
        feedback_tool,
        "resolve_pe_brain_evidence_refs",
        lambda refs, exercise_key: {
            "accepted_refs": list(refs),
            "invalid_refs": [],
            "accepted_packs": [{"id": ref, "quality_status": "accepted"} for ref in refs],
            "exercise_key": exercise_key,
        },
    )

    result = build_sports_motion_report_package({"student_name": "백종환", "exercise": "제멀"}, pdf_gate=fake_pdf_gate)

    assert result["ok"] is True
    assert result["cohort_model"]["elite_5pct_session_count"] == 1
