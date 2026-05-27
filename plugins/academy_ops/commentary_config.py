"""Routing defaults for Academy LLM commentary tasks."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


COMMENTARY_TASK = "academy_plan_commentary"
COMMENTARY_PROVIDER = "openai-codex"
COMMENTARY_MODEL = "gpt-5.4"
COMMENTARY_TIMEOUT_SECONDS = 10
COMMENTARY_OUTER_TIMEOUT_SECONDS = 28
COMMENTARY_EXTRA_BODY = {"reasoning": {"effort": "low"}}
COMMENTARY_FALLBACK_MODELS = ("gpt-5.3-codex-spark", "gpt-5.2")
COMMENTARY_FALLBACK_TIMEOUT_SECONDS = 8
COMMENTARY_TIMEOUT_MESSAGE = "미호 코멘트: 코멘트 생성이 지연돼서 이번에는 운동계획 목록만 먼저 보냈어."
COMMENTARY_ERROR_MESSAGE = "미호 코멘트: 코멘트 생성 쪽이 잠깐 막혀서 이번에는 운동계획 목록만 먼저 보냈어."
ROUTER_MODEL_TIMEOUT_SECONDS = 5
ROUTER_FALLBACK_MODELS = COMMENTARY_FALLBACK_MODELS
ROUTER_EXTRA_BODY: dict[str, Any] = {}


def plan_commentary_aux_defaults() -> dict[str, Any]:
    return {
        "provider": COMMENTARY_PROVIDER,
        "model": COMMENTARY_MODEL,
        "timeout": COMMENTARY_TIMEOUT_SECONDS,
        "extra_body": deepcopy(COMMENTARY_EXTRA_BODY),
    }
