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
# The codex auxiliary stream needs >5s, and a *cold* connection can take ~12s
# (measured on Windows; Linux cold-starts ~3.4s, well under the cap). An 8s cap
# timed out on every cold call -> the router fell back to the body agent, which
# then misrouted ("체크" -> attendance, etc.). A 15s cap still had zero headroom
# against a 12-15s cold-start (a 15s cold call raced the cap and lost), so the
# first cold request after boot / before a warm-up refresh would time out and
# degrade to the body agent. 25s fully absorbs the cold-start with margin.
# fast envs return the moment the model responds, so the higher cap costs them
# nothing. The periodic warm-up (see warmup.py) keeps the codex connection hot
# so most calls finish in ~1.6s. If it still times out, resolve_and_execute
# falls back to the body agent instead of failing the question.
ROUTER_MODEL_TIMEOUT_SECONDS = 25
ROUTER_FALLBACK_MODELS = router_fallback_models()
ROUTER_EXTRA_BODY: dict[str, Any] = {}


def plan_commentary_aux_defaults() -> dict[str, Any]:
    return {
        "provider": COMMENTARY_PROVIDER,
        "model": COMMENTARY_MODEL,
        "timeout": COMMENTARY_TIMEOUT_SECONDS,
        "extra_body": deepcopy(COMMENTARY_EXTRA_BODY),
    }
