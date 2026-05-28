from __future__ import annotations

import os
import tempfile
from contextlib import contextmanager
from typing import Any, Iterator


OPT_IN_ENV = "MIHO_PROMPTFOO_LIVE"


@contextmanager
def _temporary_miho_home(enabled: bool) -> Iterator[None]:
    if not enabled:
        yield
        return

    previous = os.environ.get("MIHO_HOME")
    with tempfile.TemporaryDirectory(prefix="miho_promptfoo_") as tmp:
        os.environ["MIHO_HOME"] = tmp
        try:
            yield
        finally:
            if previous is None:
                os.environ.pop("MIHO_HOME", None)
            else:
                os.environ["MIHO_HOME"] = previous


def _live_warning(required_env: str) -> str:
    return (
        "실제 미호 연결은 꺼져 있습니다. 비용과 실환경 오염을 막기 위해 "
        f"{required_env}=1 을 설정한 경우에만 AIAgent.chat() 평가를 실행합니다."
    )


def call_api(prompt: str, options: dict[str, Any], context: dict[str, Any]) -> dict[str, str]:
    """Promptfoo provider that calls Miho only after explicit opt-in."""
    config = options.get("config", {})
    required_env = str(config.get("requireEnv") or OPT_IN_ENV)
    if os.environ.get(required_env) != "1":
        return {"output": _live_warning(required_env)}

    temp_home = bool(config.get("tempHome", True))
    max_iterations = int(config.get("maxIterations", 1))
    provider = os.environ.get("MIHO_PROMPTFOO_PROVIDER") or config.get("provider")
    model = os.environ.get("MIHO_PROMPTFOO_MODEL") or config.get("model", "")

    try:
        with _temporary_miho_home(temp_home):
            from run_agent import AIAgent

            agent = AIAgent(
                provider=provider,
                model=model,
                max_iterations=max_iterations,
                quiet_mode=True,
                skip_memory=True,
                skip_context_files=True,
                load_soul_identity=True,
            )
            return {"output": agent.chat(prompt)}
    except Exception:
        case = context.get("vars", {}).get("case", "live")
        return {
            "output": (
                f"실제 미호 평가를 완료하지 못했습니다 ({case}). "
                "모델 설정과 인증 정보를 확인한 뒤 다시 시도해 주세요."
            )
        }
