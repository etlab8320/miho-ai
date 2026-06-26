"""Validation loop receipt scoring for Governance OS closure."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


ADVERSARIAL_VALIDATOR_TASK = "miho_governance_adversarial_validator"

_REQUIRED_TESTS = ("focused_tests", "wider_gate", "runtime_readiness")
_REQUIRED_SMOKES = ("live_gateway_smoke", "attachment_artifact_smoke")


@dataclass(frozen=True)
class ValidationLoopReport:
    ready: bool
    score: int
    failures: tuple[str, ...] = field(default_factory=tuple)
    passed: tuple[str, ...] = field(default_factory=tuple)


def run_adversarial_validator(
    *,
    test_receipts: tuple[dict[str, Any], ...],
    smoke_receipts: tuple[dict[str, Any], ...],
    change_summary: str,
    call_llm: Callable[..., Any] | None = None,
    extract_content: Callable[[Any], str] | None = None,
) -> dict[str, Any]:
    if call_llm is None or extract_content is None:
        from agent.auxiliary_client import call_llm as default_call_llm
        from agent.auxiliary_client import extract_content_or_reasoning

        call_llm = call_llm or default_call_llm
        extract_content = extract_content or extract_content_or_reasoning

    payload = {
        "change_summary": change_summary,
        "test_receipts": list(test_receipts),
        "smoke_receipts": list(smoke_receipts),
        "required_response": {
            "status": "pass|fail|retry_needed",
            "score": "0-100",
            "independent": True,
            "findings": [],
        },
    }
    messages = [
        {
            "role": "system",
            "content": (
                "You are the independent Governance OS adversarial validator. "
                "Do not trust builder claims. Return only JSON."
            ),
        },
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False, sort_keys=True)},
    ]
    response = call_llm(task=ADVERSARIAL_VALIDATOR_TASK, messages=messages)
    verdict = _json_object_from_text(extract_content(response))
    verdict.setdefault("reviewer", "adversarial_validator")
    verdict["task"] = ADVERSARIAL_VALIDATOR_TASK
    verdict["llm_receipt"] = True
    verdict["transport"] = "auxiliary_llm"
    verdict["prompt_sha256"] = _stable_digest(payload)
    return verdict


def evaluate_validation_loop(
    *,
    test_receipts: tuple[dict[str, Any], ...],
    smoke_receipts: tuple[dict[str, Any], ...],
    adversarial_reviews: tuple[dict[str, Any], ...],
) -> ValidationLoopReport:
    failures: list[str] = []
    passed: list[str] = []
    checks: list[bool] = []

    for kind in _REQUIRED_TESTS:
        ok, failure = _required_passed_receipt(test_receipts, kind, label="test")
        checks.append(ok)
        if ok:
            passed.append(kind)
        else:
            failures.append(failure)

    for kind in _REQUIRED_SMOKES:
        ok, failure = _required_passed_smoke(smoke_receipts, kind)
        checks.append(ok)
        if ok:
            passed.append(kind)
        else:
            failures.append(failure)

    review_ok = any(_adversarial_review_passed(review) for review in adversarial_reviews)
    checks.append(review_ok)
    if review_ok:
        passed.append("independent_adversarial_review")
    else:
        failures.append("missing independent adversarial review")

    score = round((sum(1 for item in checks if item) / len(checks)) * 100)
    return ValidationLoopReport(
        ready=not failures,
        score=score,
        failures=tuple(failures),
        passed=tuple(passed),
    )


def _required_passed_receipt(
    receipts: tuple[dict[str, Any], ...],
    kind: str,
    *,
    label: str,
) -> tuple[bool, str]:
    receipt = _first_kind(receipts, kind)
    if receipt is None:
        return False, f"missing required {label}: {kind}"
    if not _receipt_passed(receipt):
        return False, f"failed required {label}: {kind}"
    if not str(receipt.get("command") or "").strip():
        return False, f"missing command evidence for {kind}"
    if not str(receipt.get("evidence") or "").strip():
        return False, f"missing receipt evidence for {kind}"
    return True, ""


def _required_passed_smoke(
    receipts: tuple[dict[str, Any], ...],
    kind: str,
) -> tuple[bool, str]:
    receipt = _first_kind(receipts, kind)
    if receipt is None:
        return False, f"missing required smoke: {kind}"
    if not _receipt_passed(receipt):
        return False, f"failed required smoke: {kind}"
    if not str(receipt.get("evidence") or "").strip():
        return False, f"missing smoke evidence for {kind}"
    if kind == "live_gateway_smoke":
        mode = str(receipt.get("mode") or "").strip()
        if mode not in {"live", "live_safe"}:
            return False, "live gateway smoke must declare live or live_safe mode"
    if kind == "attachment_artifact_smoke" and not _artifact_smoke_passed(receipt):
        return False, "attachment artifact smoke did not prove deliverable MEDIA artifact"
    return True, ""


def _artifact_smoke_passed(receipt: dict[str, Any]) -> bool:
    raw_path = str(receipt.get("artifact_path") or "").strip().strip("`")
    media_tag = str(receipt.get("media_tag") or "").strip()
    if not raw_path or not media_tag.startswith("MEDIA:"):
        return False
    try:
        path = Path(raw_path).expanduser().resolve(strict=True)
    except (OSError, RuntimeError, ValueError):
        return False
    return path.is_file() and raw_path in media_tag


def _adversarial_review_passed(review: dict[str, Any]) -> bool:
    if review.get("llm_receipt") is not True:
        return False
    if str(review.get("transport") or "").strip() != "auxiliary_llm":
        return False
    if not str(review.get("prompt_sha256") or "").strip():
        return False
    if str(review.get("status") or "").strip() not in {"pass", "passed"}:
        return False
    if review.get("independent") is not True:
        return False
    if str(review.get("task") or "").strip() != ADVERSARIAL_VALIDATOR_TASK:
        return False
    if str(review.get("reviewer") or "").strip().casefold() in {"", "builder", "self"}:
        return False
    if _score(review.get("score")) < 95:
        return False
    findings = review.get("findings")
    return isinstance(findings, list) and len(findings) == 0


def _first_kind(receipts: tuple[dict[str, Any], ...], kind: str) -> dict[str, Any] | None:
    for receipt in receipts:
        if str(receipt.get("kind") or "") == kind:
            return receipt
    return None


def _receipt_passed(receipt: dict[str, Any]) -> bool:
    status = str(receipt.get("status") or "").strip()
    exit_code = receipt.get("exit_code")
    return status in {"pass", "passed", "success"} and exit_code in {None, 0}


def _score(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _json_object_from_text(text: str) -> dict[str, Any]:
    raw = str(text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
        if not match:
            return {"status": "fail", "score": 0, "independent": False, "findings": ["invalid_json"]}
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            return {"status": "fail", "score": 0, "independent": False, "findings": ["invalid_json"]}
    if not isinstance(parsed, dict):
        return {"status": "fail", "score": 0, "independent": False, "findings": ["invalid_json"]}
    return parsed


def _stable_digest(value: dict[str, Any]) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
