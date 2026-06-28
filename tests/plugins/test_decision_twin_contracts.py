"""Decision Twin tool contract and region-gate regressions."""

from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest

from plugins.decision_twin import _decision_twin_pre_gateway_dispatch
from plugins.decision_twin.contracts import decision_tool_contracts
from plugins.decision_twin.contract_schema import REQUIRED_CONTRACT_FIELDS


def test_decision_contracts_cover_every_registered_tool() -> None:
    from miho_cli.plugins import discover_plugins
    from tools.registry import discover_builtin_tools, registry

    discover_builtin_tools()
    discover_plugins(force=True)

    contracts = decision_tool_contracts()
    registered_tools = set(registry.get_all_tool_names())
    missing = sorted(registered_tools - set(contracts))

    assert missing == []
    assert contracts["send_message"]["domain"] == "messaging"
    assert contracts["terminal"]["domain"] == "terminal"
    assert contracts["academy_student_card_image"]["domain"] == "academy_ops"


def test_core_contracts_use_full_agentic_schema() -> None:
    contracts = decision_tool_contracts()
    required_tools = (
        "html_pdf_quality_gate",
        "media_delivery_contract",
        "academy_hakjong_report_package",
        "academy_practical_reco_all_candidates",
        "academy_thread_roster_lookup",
        "susi27_recommend_candidates",
        "susi27_score_calculate",
        "life_record_summary",
    )

    for tool_name in required_tools:
        contract = contracts[tool_name]
        missing = REQUIRED_CONTRACT_FIELDS - set(contract)
        assert missing == set(), f"{tool_name} missing {sorted(missing)}"
        assert contract["purpose"]
        assert contract["required_inputs"]
        assert contract["output"]
        assert contract["reviewer"]
        assert contract["retry"]
        assert contract["delivery"]


def test_core_domain_contracts_are_not_generic_fallbacks() -> None:
    contracts = decision_tool_contracts()
    core_tools = (
        "life_record_ingest_pdf",
        "life_record_summary",
        "life_record_lookup",
        "academy_hakjong_report_package",
        "academy_render_image",
        "academy_report_image",
        "send_message",
        "jungsi_login",
    )

    for tool_name in core_tools:
        contract = contracts[tool_name]
        purpose = contract["purpose"]
        assert len(purpose) >= 35
        assert not purpose.startswith("Registered Miho tool")
        assert contract["domain"]


def test_hakjong_contract_forbids_final_answer_on_repairable_rejection() -> None:
    purpose = decision_tool_contracts()["academy_hakjong_report_package"]["purpose"]

    assert "반려" in purpose
    assert "같은 턴" in purpose
    assert "최종 답변 금지" in purpose
    assert "다음 턴" not in purpose


def test_optional_schema_args_are_not_all_marked_required() -> None:
    contract = decision_tool_contracts()["sports_max_analysis_variables"]

    assert contract["required_inputs"] == ["user request"]
    assert "student_name" in contract["optional_inputs"]
    assert "sport" in contract["optional_inputs"]
    assert set(contract["optional_inputs"]) == set(contract["args"])


def test_runtime_diagnostic_contracts_separate_live_state_from_memory() -> None:
    contracts = decision_tool_contracts()
    terminal_purpose = contracts["terminal"]["purpose"]
    session_search_purpose = contracts["session_search"]["purpose"]

    assert "현재" in terminal_purpose
    assert "SSH" in terminal_purpose
    assert "크론" in terminal_purpose
    assert "직접 확인" in terminal_purpose
    assert "과거 대화" in session_search_purpose
    assert "현재" in session_search_purpose
    assert "terminal" in session_search_purpose


def test_domain_guard_module_absent() -> None:
    """domain_guard.py가 삭제됐으므로 import가 실패해야 한다."""

    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("plugins.decision_twin.domain_guard")


@pytest.mark.asyncio
async def test_region_gate_asks_before_recommendation() -> None:
    """추천 라우팅인데 지역 미언급이면 현관에서 지역 질문을 직접 보낸다."""

    async def resolver(_messages):
        return {
            "action": "route",
            "required_tool": "susi27_recommend_candidates",
            "intent": "실기전형 추천",
            "confidence": 0.95,
            "needs_region_question": True,
        }

    event = SimpleNamespace(
        text="종환이 실기전형 6개 추천해줘",
        source=object(),
        media_urls=[],
        reply_to_text="",
        channel_context="",
        channel_prompt="",
    )
    gateway = SimpleNamespace(_is_user_authorized=lambda _source: True)
    result = await _decision_twin_pre_gateway_dispatch(
        event=event,
        gateway=gateway,
        resolver=resolver,
        owner_context_builder=lambda _text: "",
    )

    assert result["action"] == "respond"
    assert result["reason"] == "region_gate"
    assert "지역" in result["text"]


@pytest.mark.asyncio
async def test_region_gate_passes_when_region_mentioned() -> None:
    async def resolver(_messages):
        return {
            "action": "route",
            "required_tool": "susi27_recommend_candidates",
            "intent": "실기전형 추천",
            "confidence": 0.95,
            "needs_region_question": False,
        }

    event = SimpleNamespace(
        text="종환이 실기전형 강원·경기로 추천해줘",
        source=object(),
        media_urls=[],
        reply_to_text="",
        channel_context="",
        channel_prompt="",
    )
    gateway = SimpleNamespace(_is_user_authorized=lambda _source: True)
    result = await _decision_twin_pre_gateway_dispatch(
        event=event,
        gateway=gateway,
        resolver=resolver,
        owner_context_builder=lambda _text: "",
    )

    assert result["action"] == "rewrite"


@pytest.mark.asyncio
async def test_decision_twin_rewrite_preserves_llm_tool_args() -> None:
    async def resolver(_messages):
        return {
            "action": "route",
            "required_tool": "academy_practical_reco_all_candidates",
            "intent": "김서연 수도권·강원·충청권 수시 실기전형 전체 추천 PDF 생성",
            "confidence": 0.98,
            "needs_region_question": False,
            "region_value": "수도권, 강원, 충청",
            "tool_args": {
                "student_name": "김서연",
                "region": "수도권, 강원, 충청",
            },
        }

    event = SimpleNamespace(
        text="서연이 수시 실기전형으로 수도권,강원 충청권으로 학교 추천 다 해서 pdf로 줘",
        source=object(),
        media_urls=[],
        reply_to_text="",
        channel_context="",
        channel_prompt="",
    )
    gateway = SimpleNamespace(_is_user_authorized=lambda _source: True)
    result = await _decision_twin_pre_gateway_dispatch(
        event=event,
        gateway=gateway,
        resolver=resolver,
        owner_context_builder=lambda _text: "",
    )

    assert result["action"] == "rewrite"
    text = str(result["text"])
    assert "도구 인자(JSON)" in text
    assert '"student_name": "김서연"' in text
    assert '"region": "수도권, 강원, 충청"' in text
