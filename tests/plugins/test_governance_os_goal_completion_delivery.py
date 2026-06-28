"""Goal-completion delivery regressions for user-visible Miho failures."""

from __future__ import annotations

import importlib
import json
from typing import cast

from plugins.governance_os.delivery_gate import governance_transform_llm_output


def test_verified_pdf_conflict_copy_is_replaced_with_attachment(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MIHO_HOME", str(tmp_path / "miho_home"))

    import gateway.platforms.base as base
    import miho_constants

    importlib.reload(miho_constants)
    importlib.reload(base)

    media_dir = tmp_path / "miho_home" / "media_cache" / "susi-summary"
    media_dir.mkdir(parents=True)
    pdf = media_dir / "김서연_실기전형전체추천_15.pdf"
    pdf.write_bytes(b"%PDF-1.4\nlatest\n")

    transformed = governance_transform_llm_output(
        response_text=(
            "ㅋㅋ 맥스, 지금 확인 가능한 정보로는 서연이 수시 실기전형 수도권·강원·충청권 "
            "전체 후보 추천 PDF를 '검증 통과본'으로 확정해서 전달할 수 없어.\n\n"
            "그래서 현재는 PDF 첨부 대신 상태만 말하면: 검증 완료본으로 확인되지 않음."
        ),
        user_message="서연이 수시 실기전형 수도권·강원·충청권 전체 후보 추천 PDF로 줘",
        conversation_history=[
            {
                "role": "user",
                "content": "서연이 수시 실기전형 수도권·강원·충청권 전체 후보 추천 PDF로 줘",
            },
            {
                "role": "tool",
                "name": "academy_practical_reco_all_candidates",
                "content": json.dumps(
                    {
                        "ok": True,
                        "file_path": str(pdf),
                        "media_tag": f"MEDIA:{pdf}",
                        "reviewer": {
                            "name": "academy_result_reviewer",
                            "status": "pass",
                            "checked": ["내용", "근거", "요청 의도"],
                        },
                    },
                    ensure_ascii=False,
                ),
            },
        ],
        governance_outcomes=[],
        final_delivery_call_llm=_pass_through_final_delivery_agent,
        final_delivery_extract_content=_extract_content,
    )

    assert transformed is not None
    assert transformed.startswith("여기 있어.")
    assert transformed.count("MEDIA:") == 1
    assert str(pdf) in transformed
    assert "검증 통과본" not in transformed
    assert "전달할 수 없어" not in transformed
    assert "확인되지 않음" not in transformed
    assert base.resolve_media_delivery_path(transformed.split("MEDIA:", 1)[1].strip("` \n"))


def test_terminal_diagnosis_evidence_reaches_final_delivery_agent() -> None:
    seen: dict[str, object] = {}

    def final_agent(*_args: object, **kwargs: object) -> dict[str, object]:
        seen.update(kwargs)
        return {
            "content": json.dumps(
                {
                    "action": "revise",
                    "answer": (
                        "확인 결과 n100 SSH 22번 접속이 타임아웃입니다. "
                        "Hermes/Miho 부재로 단정할 단계가 아니라, 현재 막힌 지점은 n100 접속 경로입니다."
                    ),
                },
                ensure_ascii=False,
            )
        }

    transformed = governance_transform_llm_output(
        response_text=(
            "n100 수집 실패는 접속 문제일 가능성을 먼저 봐야 해. "
            "그다음 Hermes/Miho 프로세스를 확인해야 해."
        ),
        user_message="n100 수집실패는 왜그런거야? 헤르메스나 미호가 없어서그런거야?",
        conversation_history=[
            {
                "role": "user",
                "content": "n100 수집실패는 왜그런거야? 헤르메스나 미호가 없어서그런거야?",
            },
            {
                "role": "tool",
                "name": "terminal",
                "content": (
                    "== n100 reachability now ==\n"
                    "ssh: connect to host n100 port 22: Operation timed out\n"
                    "exit_code=255"
                ),
            },
        ],
        governance_outcomes=[],
        final_delivery_call_llm=final_agent,
        final_delivery_extract_content=_extract_content,
    )

    assert transformed is not None
    assert "SSH 22번 접속이 타임아웃" in transformed
    assert "가능성" not in transformed
    messages = seen["messages"]
    assert isinstance(messages, list)
    prompt = json.loads(str(messages[1]["content"]).split("EVIDENCE: ", 1)[1])
    assert prompt["current_turn_tool_evidence"][0]["tool_name"] == "terminal"
    assert "Operation timed out" in prompt["current_turn_tool_evidence"][0]["content"]


def _pass_through_final_delivery_agent(*_args: object, **_kwargs: object) -> dict[str, object]:
    messages = _kwargs.get("messages")
    assert isinstance(messages, list)
    prompt = str(messages[-1]["content"])
    answer = prompt.split("\nEVIDENCE: ", 1)[0].split("\nA: ", 1)[1]
    return {"content": json.dumps({"action": "deliver", "answer": answer}, ensure_ascii=False)}


def _extract_content(response: object) -> str:
    assert isinstance(response, dict)
    if isinstance(response, dict):
        typed = cast("dict[str, object]", response)
        return str(typed.get("content") or "")
    return str(response or "")
