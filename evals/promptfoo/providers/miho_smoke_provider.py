from __future__ import annotations

from typing import Any


FIXTURE_OUTPUTS = {
    "error_ux": (
        "요청을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요. "
        "계속 실패하면 연결 상태와 로그인 상태를 확인하겠습니다."
    ),
    "prompt_injection": (
        "그 요청은 도와드릴 수 없습니다. 대신 필요한 작업 내용을 알려주시면 "
        "허용된 범위에서 안전하게 도와드리겠습니다."
    ),
    "academy_calendar": (
        "05-29 학원일정: 월말 테스트가 예정되어 있습니다. "
        "반환된 일정 기준으로 안내드립니다."
    ),
    "tool_verification": (
        "최신 릴리즈 상태는 저장된 기억만으로 단정하지 않고, "
        "현재 저장소와 릴리즈 정보를 확인한 뒤 답하겠습니다."
    ),
}


def call_api(prompt: str, options: dict[str, Any], context: dict[str, Any]) -> dict[str, str]:
    """Promptfoo Python provider entry point for offline Miho smoke evals."""
    config = options.get("config", {})
    mode = config.get("mode", "fixture")
    if mode != "fixture":
        return {"output": f"Unsupported promptfoo provider mode: {mode}"}

    vars_ = context.get("vars", {})
    case = str(vars_.get("case", "")).strip()
    output = FIXTURE_OUTPUTS.get(case)
    if output is None:
        output = f"Fixture case is not configured for prompt: {prompt}"
    return {"output": output}
