"""Academy reviewer bridge tests for Governance OS."""

from __future__ import annotations

import importlib

from plugins.governance_os.academy_bridge import record_academy_review_outcome


def _reload_evolution_home(tmp_path, monkeypatch):
    monkeypatch.setenv("MIHO_HOME", str(tmp_path / "miho_home"))

    import miho_constants
    from agent import evolution

    importlib.reload(miho_constants)
    importlib.reload(evolution)
    return evolution


def test_academy_review_failure_records_retry_tool(tmp_path, monkeypatch) -> None:
    evolution = _reload_evolution_home(tmp_path, monkeypatch)

    record_academy_review_outcome(
        "academy_hakjong_report_package",
        {
            "ok": False,
            "file_path": "/tmp/report.pdf",
            "errors": ["layout overflow"],
            "reviewer": {
                "name": "academy_result_reviewer",
                "status": "blocked",
            },
        },
    )

    outcome = evolution.list_events(limit=1)[0]["metadata"]["governance_outcome"]
    assert outcome["playbook_key"] == "academy_hakjong_report"
    assert outcome["review_status"] == "blocked"
    assert outcome["retry_tools"] == ["academy_hakjong_report_package"]


def test_susi_score_review_records_dedicated_score_playbook(tmp_path, monkeypatch) -> None:
    evolution = _reload_evolution_home(tmp_path, monkeypatch)

    record_academy_review_outcome(
        "susi27_score_calculate",
        {
            "status": "calculated",
            "student_record_score": 947.3,
            "reviewer": {
                "name": "academy_result_reviewer",
                "status": "pass",
                "checked": ["필수 산출 필드", "상태값"],
            },
        },
    )

    outcome = evolution.list_events(limit=1)[0]["metadata"]["governance_outcome"]
    assert outcome["playbook_key"] == "susi_score_calculation"
    assert outcome["tools_used"] == ["susi27_score_calculate"]
    assert outcome["review_status"] == "pass"
