"""Routing defaults for Academy LLM commentary tasks."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .codex_model_policy import (
    commentary_fallback_models,
    commentary_model,
    codex_provider,
    router_fallback_models,
    router_model,
)


COMMENTARY_TASK = "academy_plan_commentary"
COMMENTARY_PROVIDER = codex_provider()
COMMENTARY_MODEL = commentary_model()
COMMENTARY_TIMEOUT_SECONDS = 10
COMMENTARY_OUTER_TIMEOUT_SECONDS = 28
COMMENTARY_EXTRA_BODY = {"reasoning": {"effort": "low"}}
COMMENTARY_FALLBACK_MODELS = commentary_fallback_models()
COMMENTARY_FALLBACK_TIMEOUT_SECONDS = 8
COMMENTARY_TIMEOUT_MESSAGE = "미호 코멘트: 코멘트 생성이 지연돼서 이번에는 운동계획 목록만 먼저 보냈어."
COMMENTARY_ERROR_MESSAGE = "미호 코멘트: 코멘트 생성 쪽이 잠깐 막혀서 이번에는 운동계획 목록만 먼저 보냈어."
ROUTER_MODEL = router_model()
# The codex auxiliary stream routinely needs >5s, so a 5s cap made the router
# (intent shortcut) fail almost every call. 8s lets it succeed when it can; if
# it still times out, resolve_and_execute now falls back to the body agent
# instead of failing the question.
ROUTER_MODEL_TIMEOUT_SECONDS = 8
ROUTER_FALLBACK_MODELS = router_fallback_models()
ROUTER_EXTRA_BODY: dict[str, Any] = {}


def plan_commentary_aux_defaults() -> dict[str, Any]:
    return {
        "provider": COMMENTARY_PROVIDER,
        "model": COMMENTARY_MODEL,
        "timeout": COMMENTARY_TIMEOUT_SECONDS,
        "extra_body": deepcopy(COMMENTARY_EXTRA_BODY),
    }
