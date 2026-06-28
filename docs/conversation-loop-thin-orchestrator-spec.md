# Conversation Loop Thin Orchestrator Spec

## Problem

`agent/conversation_loop.py` is the live turn runner for Miho, but it is too large
to review safely. The file must become a thin turn orchestrator while preserving
gateway, CLI, tool-calling, session persistence, interrupt, and Governance OS
behavior.

## Scope

### In

- Split cohesive turn-loop responsibilities into runtime modules under `agent/`.
- Keep every new or touched runtime file at 500 lines or less.
- Preserve the public `run_conversation(...)` import contract.
- Preserve LLM-based Governance OS routing, verification, Final QA, and hook behavior.
- Add or update tests before each behavior-sensitive extraction.

### Out

- No provider rewrite.
- No gateway protocol rewrite.
- No UI/chat surface rewrite.
- No deployment, restart, or production config changes.

## Acceptance Criteria

- `agent/conversation_loop.py` is a readable orchestrator and no longer a 4000-line
  implementation file.
- No new runtime file exceeds 500 lines.
- Final output hook behavior remains fail-closed for gateway surfaces.
- `run_conversation` contract remains compatible with existing callers.
- Focused conversation/hook tests pass after each extraction.
- Governance OS wider tests pass before completion.
- Diff review has no high finding caused by `agent/conversation_loop.py`.

## Test Plan

- Focused: `scripts/run_tests.sh tests/test_transform_llm_output_hook.py`
- Focused gateway/governance: `scripts/run_tests.sh tests/plugins/test_governance_os*.py tests/e2e/test_governance_os_subagent_routing_smoke.py`
- Static: `ruff check` on changed Python files.
- Compile: `python -m compileall` on changed runtime modules.
- Advisory: `et-diff-review.py --root /Users/etlab/projects/miho-ai`

## Risks

- The loop has many implicit locals; large extraction can silently alter state.
- Interrupt, incomplete response, and streaming paths are high risk.
- Existing unrelated oversized runtime files remain outside this task unless touched.

## 2026-06-27 Completion Receipt

- `agent/conversation_loop.py`: 477 lines, thin turn orchestrator.
- Adjacent extracted modules: request setup/finalization, API request/attempt/success,
  response validation, length recovery, error recovery, response processing,
  tool response, text response, iteration support, runtime context, Nous preflight,
  image shrink.
- Touched conversation runtime files are 500 lines or less.
- `agent/conversation_compression.py` was reduced from 603 to 494 lines by moving
  image shrink recovery to `agent/conversation_image_shrink.py`.
- Tests:
  - `scripts/run_tests.sh tests/run_agent tests/cli/test_surrogate_sanitization.py`
    → 1454 passed, 0 failed.
  - `scripts/run_tests.sh tests/plugins/test_governance_os_*.py tests/test_transform_llm_output_hook.py`
    → 280 passed, 0 failed.
  - Compression focused set → 478 passed, 0 failed.
- Runtime checks:
  - `miho governance status --json`: `full_system_score=100`,
    `readiness_quality_score=100`, `self_harness_quality_score=100`.
  - `miho governance live-check --json`: live-safe gateway/artifact preflight ready,
    no actual send attempted in that command.

## Adversarial Closure

Conversation loop scope: 100/100 candidate.

Rationale:

- The live loop is now an orchestrator rather than the implementation body.
- State-sensitive branches are covered by run_agent, Codex responses, compression,
  image recovery, Unicode/surrogate, and Governance hook tests.
- The final output hook remains fail-closed on gateway surfaces.
- No touched conversation runtime file exceeds 500 lines.

Residual outside this scope:

- The broader `agent/` package still has pre-existing oversized runtime files.
  That remains a repository-wide maintainability item, not a blocker for the
  conversation-loop closure.
