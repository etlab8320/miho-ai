"""LLM-structured natural request router for academy operations."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging
from typing import Any, Awaitable, Callable, ClassVar

from .assignment_followup import assignment_count_followup_response
from .commentary_config import (
    COMMENTARY_EXTRA_BODY,
    COMMENTARY_FALLBACK_TIMEOUT_SECONDS,
    COMMENTARY_PROVIDER,
    ROUTER_EXTRA_BODY,
    ROUTER_FALLBACK_MODELS,
    ROUTER_MODEL,
    ROUTER_MODEL_TIMEOUT_SECONDS,
)
from .natural_router_prompt import build_resolver_messages
from .natural_router_payload import (
    is_login_required_payload,
    load_payload,
    payload_message,
    response_content,
    today_kst,
    tool_timeout_message,
)
from .guidance_copy import naturalize_guidance_response
from .response_commentary import append_summary_comment_or_fallback
from .response_focus import focused_response
from .response_synthesis import compact_payload, synthesize_or_fallback
from .route_overrides import forced_tool_for_output_request, should_render_attendance_day_image
from .route_arg_normalization import normalize_route_args, normalize_route_decision_tools
from .routing_decision import reject_execute_reason
from .route_plan import execute_route_plan
from .student_record_fast_path import try_student_record_chart_fast_path, try_student_record_fast_path
from .thread_context import (
    INHERITABLE_ENTITY_ARGS,
    MONTHLY_TEST_CONTEXT_TOOLS,
    _is_blank,
    get_thread_context,
    pop_pending_request,
    remember_pending_request,
    remember_thread_context,
)
from .tool_registry import TOOL_CONTRACTS, TOOL_HANDLERS, ToolHandler


logger = logging.getLogger(__name__)
Resolver = Callable[[list[dict[str, str]]], Awaitable[Any]]
ROUTER_TASK = "academy_request_router"
# Outer wait_for must exceed the primary model cap and leave fallback room.
ROUTER_TIMEOUT_SECONDS = 28
ROUTER_MAX_ATTEMPTS = 1
TOOL_TIMEOUT_SECONDS = 70
MIN_CONFIDENCE = 0.55
TIMEOUT_RESPONSE = "지금 학원 서버 응답이 불안정해서 요청을 처리하지 못했어. 잠시 후 다시 한 번 보내줘."


@dataclass(frozen=True)
class AcademyNaturalRoute:
    action: str
    response_text: str = ""
    reason: str = ""

    ALLOW: ClassVar[str] = "allow"
    HANDLED: ClassVar[str] = "handled"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, str):
            return self.action == other
        return super().__eq__(other)


async def default_resolver(messages: list[dict[str, str]]) -> Any:
    from agent.auxiliary_client import async_call_llm

    last_exc: Exception | None = None
    model_sequence = (ROUTER_MODEL, *ROUTER_FALLBACK_MODELS)
    for index, model in enumerate(model_sequence):
        try:
            return await async_call_llm(
                task=ROUTER_TASK,
                provider=COMMENTARY_PROVIDER,
                model=model,
                messages=messages,
                temperature=0,
                max_tokens=260,
                timeout=(
                    ROUTER_MODEL_TIMEOUT_SECONDS
                    if index == 0
                    else COMMENTARY_FALLBACK_TIMEOUT_SECONDS
                ),
                extra_body=ROUTER_EXTRA_BODY,
            )
        except Exception as exc:
            last_exc = exc
            logger.info("academy request resolver model failed: %s (%s)", model, exc)
    raise last_exc or TimeoutError()


async def resolve_and_execute_academy_request(
    text: str,
    *,
    resolver: Resolver = default_resolver,
    handlers: dict[str, ToolHandler] | None = None,
    today: str | None = None,
    resolver_timeout: float = ROUTER_TIMEOUT_SECONDS,
    resolver_attempts: int = ROUTER_MAX_ATTEMPTS,
    tool_timeout: float = TOOL_TIMEOUT_SECONDS,
    synthesize: bool = True,
    context_key: str | None = None,
    default_student_query: str | None = None,
) -> AcademyNaturalRoute:
    clean = text.strip()
    if not clean or clean.startswith("/"):
        return AcademyNaturalRoute(AcademyNaturalRoute.ALLOW)
    if response := assignment_count_followup_response(clean, get_thread_context(context_key)):
        return AcademyNaturalRoute(AcademyNaturalRoute.HANDLED, response, "assignment_count_followup")
    pending_route = await _try_pending_request_retry(
        clean,
        handlers=handlers,
        tool_timeout=tool_timeout,
        synthesize=synthesize,
        context_key=context_key,
    )
    if pending_route is not None:
        return pending_route
    fast_chart_response = await try_student_record_chart_fast_path(
        clean, handlers=handlers or TOOL_HANDLERS, tool_timeout=tool_timeout, today=today, context_key=context_key
    )
    if fast_chart_response is not None:
        return AcademyNaturalRoute(AcademyNaturalRoute.HANDLED, fast_chart_response, "student_record_chart_fast_path")
    fast_record_response = await try_student_record_fast_path(
        clean, handlers=handlers or TOOL_HANDLERS, tool_timeout=tool_timeout, today=today, context_key=context_key
    )
    if fast_record_response is not None:
        return AcademyNaturalRoute(AcademyNaturalRoute.HANDLED, fast_record_response, "student_record_fast_path")
    try:
        decision = await _resolve_decision_with_retry(
            clean,
            resolver,
            today=today,
            context_key=context_key,
            resolver_timeout=resolver_timeout,
            attempts=resolver_attempts,
        )
    except TimeoutError:
        logger.info("academy request resolver timed out -> ALLOW (body agent handles)")
        return AcademyNaturalRoute(AcademyNaturalRoute.ALLOW, reason="resolver_timeout")
    except Exception as exc:
        logger.info("academy request resolver failed: %s", exc)
        return AcademyNaturalRoute(AcademyNaturalRoute.ALLOW, reason="resolver_error")

    decision = normalize_route_decision_tools(clean, decision)
    tool_name = str(decision.get("tool") or "").strip()
    active_handlers = handlers or TOOL_HANDLERS
    plan_response = await execute_route_plan(
        decision,
        handlers=active_handlers,
        min_confidence=MIN_CONFIDENCE,
        tool_timeout=tool_timeout,
        today=today,
        context_key=context_key,
        resolve_args=lambda tool, route_args, key: _resolved_args(
            tool,
            route_args,
            key,
            default_student_query=default_student_query,
        ),
        with_reference_today=_with_reference_today,
    )
    if plan_response is not None:
        return AcademyNaturalRoute(AcademyNaturalRoute.HANDLED, plan_response, "route_plan")
    reject_reason = reject_execute_reason(
        decision,
        allowed_tools=active_handlers.keys(),
        min_confidence=MIN_CONFIDENCE,
    )
    if reject_reason:
        return AcademyNaturalRoute(AcademyNaturalRoute.ALLOW, reason=reject_reason)
    forced_tool = forced_tool_for_output_request(clean, tool_name)
    force_default_response = forced_tool == "academy_student_attendance_calendar_image"
    if forced_tool:
        tool_name = forced_tool
    handler = active_handlers.get(tool_name)
    if handler is None:
        return AcademyNaturalRoute(AcademyNaturalRoute.ALLOW, reason="unknown_tool")
    args = _resolved_args(
        tool_name,
        decision.get("args") if isinstance(decision.get("args"), dict) else {},
        context_key,
        default_student_query=default_student_query,
    )
    if should_render_attendance_day_image(clean, tool_name):
        args["image"] = True
    args = _with_reference_today(tool_name, args, today)
    args = normalize_route_args(tool_name, args, today=today)
    # 원문을 kwargs로 함께 넘겨, LLM이 event 인자를 잘못 추출해도 도구가 원문에서 회수.
    handler_kwargs = {"source_text": clean} if tool_name in MONTHLY_TEST_CONTEXT_TOOLS else {}
    try:
        raw_result = await asyncio.wait_for(
            asyncio.to_thread(handler, args, **handler_kwargs),
            timeout=tool_timeout,
        )
    except TimeoutError:
        return AcademyNaturalRoute(AcademyNaturalRoute.HANDLED, tool_timeout_message(), "tool_timeout")
    except Exception as exc:
        logger.info("academy tool execution failed: %s", exc)
        return AcademyNaturalRoute(AcademyNaturalRoute.HANDLED, "학원 데이터를 조회하다가 오류가 났어.")

    payload = load_payload(raw_result)
    if is_login_required_payload(payload):
        remember_pending_request(
            context_key,
            tool_name=tool_name,
            args=args,
            request_text=clean,
            reason="auth_required",
        )
    remember_thread_context(context_key, tool_name=tool_name, args=args, payload=payload)
    response_focus = "" if force_default_response else str(decision.get("response_focus") or "").strip()
    response = focused_response(payload, response_focus) or payload_message(payload)
    if decision.get("skip_synthesis"):
        response = payload_message(payload)
    elif response_focus == "summary" and synthesize and payload.get("ok") and not payload.get("media_tag"):
        response = await append_summary_comment_or_fallback(clean, compact_payload(payload), response)
    elif not response_focus and synthesize and payload.get("ok") and not payload.get("media_tag"):
        response = await synthesize_or_fallback(clean, payload, response)
    elif synthesize and payload.get("ok") is False:
        response = await naturalize_guidance_response(
            user_text=clean,
            intent=f"{tool_name}.not_ok",
            fallback=response,
        )
    return AcademyNaturalRoute(AcademyNaturalRoute.HANDLED, response, tool_name)


async def _resolve_decision_with_retry(
    text: str,
    resolver: Resolver,
    *,
    today: str | None,
    context_key: str | None,
    resolver_timeout: float,
    attempts: int = ROUTER_MAX_ATTEMPTS,
) -> dict[str, Any]:
    last_error: TimeoutError | None = None
    for attempt in range(max(1, attempts)):
        try:
            return await asyncio.wait_for(
                _resolve_decision(text, resolver, today=today, context_key=context_key),
                timeout=resolver_timeout,
            )
        except TimeoutError as exc:
            last_error = exc
            logger.info(
                "academy request resolver timed out: attempt %s/%s",
                attempt + 1,
                max(1, attempts),
            )
    raise last_error or TimeoutError()


async def _resolve_decision(
    text: str,
    resolver: Resolver,
    *,
    today: str | None,
    context_key: str | None,
) -> dict[str, Any]:
    reference_day = today or today_kst()
    response = await resolver(_resolver_messages(text, reference_day, get_thread_context(context_key)))
    payload = load_payload(response_content(response))
    return payload if isinstance(payload, dict) else {}


def _resolver_messages(
    text: str,
    today: str,
    thread_context: dict[str, Any] | None = None,
    temporal_context: str | None = None,
) -> list[dict[str, str]]:
    return build_resolver_messages(
        text,
        today,
        thread_context,
        TOOL_CONTRACTS,
        temporal_context=temporal_context,
    )


def _resolved_args(
    tool_name: str,
    args: dict[str, Any],
    context_key: str | None,
    *,
    default_student_query: str | None = None,
) -> dict[str, Any]:
    """Fill follow-up args left implicit from the last academy turn."""
    context = get_thread_context(context_key)
    contract_args = TOOL_CONTRACTS.get(tool_name, {}).get("args", [])
    resolved = dict(args)
    if (
        "student_query" in contract_args
        and _is_blank(resolved.get("student_query"))
        and not _is_blank(default_student_query)
    ):
        resolved["student_query"] = str(default_student_query).strip()
    if not context:
        return resolved
    for name in INHERITABLE_ENTITY_ARGS:
        if name in contract_args and _is_blank(resolved.get(name)) and not _is_blank(context.get(name)):
            resolved[name] = context[name]
    # Carry date ranges only for subject-scoped queries.
    has_entity_arg = any(name in contract_args for name in INHERITABLE_ENTITY_ARGS)
    if has_entity_arg and "start_date" in contract_args:
        if _is_blank(resolved.get("start_date")) and context.get("start_date"):
            resolved["start_date"] = context["start_date"]
        if _is_blank(resolved.get("end_date")) and context.get("end_date"):
            resolved["end_date"] = context["end_date"]
    # Monthly test: keep looking at the same test when not re-specified.
    if "test_id" in contract_args and "test_month" in contract_args:
        if resolved.get("test_id") is None and _is_blank(resolved.get("test_month")):
            if context.get("test_id") is not None:
                resolved["test_id"] = context["test_id"]
            elif context.get("test_month"):
                resolved["test_month"] = context["test_month"]
    return resolved


def _with_reference_today(tool_name: str, args: dict[str, Any], today: str | None) -> dict[str, Any]:
    if "today" not in TOOL_CONTRACTS.get(tool_name, {}).get("args", []):
        return args
    if str(args.get("today") or "").strip():
        return args
    resolved = dict(args)
    resolved["today"] = today or today_kst()
    return resolved


async def _try_pending_request_retry(
    text: str,
    *,
    handlers: dict[str, ToolHandler] | None,
    tool_timeout: float,
    synthesize: bool,
    context_key: str | None,
) -> AcademyNaturalRoute | None:
    pending = get_thread_context(context_key)
    if pending.get("kind") != "pending_request":
        return None
    tool_name = str(pending.get("tool") or "")
    args = pending.get("args") if isinstance(pending.get("args"), dict) else {}
    handler = (handlers or TOOL_HANDLERS).get(tool_name)
    if handler is None:
        pop_pending_request(context_key)
        return None
    try:
        raw_result = await asyncio.wait_for(asyncio.to_thread(handler, args), timeout=tool_timeout)
    except TimeoutError:
        return AcademyNaturalRoute(AcademyNaturalRoute.HANDLED, tool_timeout_message(), "pending_tool_timeout")
    except Exception as exc:
        logger.info("academy pending request retry failed: %s", exc)
        return AcademyNaturalRoute(AcademyNaturalRoute.HANDLED, "학원 데이터를 다시 조회하다가 오류가 났어.")
    pop_pending_request(context_key)
    payload = load_payload(raw_result)
    if is_login_required_payload(payload):
        remember_pending_request(context_key, tool_name=tool_name, args=args, request_text=text, reason="auth_required")
    remember_thread_context(context_key, tool_name=tool_name, args=args, payload=payload)
    response = payload_message(payload)
    if synthesize and payload.get("ok") and not payload.get("media_tag"):
        response = await synthesize_or_fallback(text, payload, response)
    elif synthesize and payload.get("ok") is False:
        response = await naturalize_guidance_response(
            user_text=text,
            intent=f"{tool_name}.not_ok",
            fallback=response,
        )
    return AcademyNaturalRoute(AcademyNaturalRoute.HANDLED, response, "pending_request_retry")
