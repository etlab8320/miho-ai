# Miho Routing Decision Twin Spec

## Problem
Miho can still answer from a generic route when a turn has enough context to use a dedicated tool. Owner rules and prior corrections must influence routing without brittle keyword checks.

## Users And Jobs
ET needs Miho to infer the current job from the user text, thread context, owner memory, and plugin evidence, then call the right tool before producing a user-visible answer.

## Scope
### In
- Run an LLM-backed pre-gateway judge for authorized user turns.
- Rank structured pre-dispatch candidates with a tool-first decision policy.
- Preserve route evidence in logs and tests.
- Inject a compact decision-twin prompt into Discord workspace context.
- Avoid routing from isolated keyword matching in the central policy.

### Out
- Training or fine-tuning a model.
- Adding new academy/life-record tools.
- Restarting production services.

## Acceptance Criteria
- A decisive candidate with `required_tool` cannot lose to a generic response solely because the generic candidate has a higher priority.
- When no domain plugin has produced a candidate yet, the LLM decision twin can return a structured `required_tool` route and rewrite the turn for the body agent.
- Every currently registered Miho tool has a decision-twin contract generated from registry metadata or an explicit domain override.
- Unauthorized or unauthenticated gateway senders do not trigger owner-memory recall or the LLM judge.
- The decision object records the decision-twin policy state and memory evidence.
- Discord workspace prompts tell Miho to infer intent from current text, thread memory, and owner profile before answering.
- Existing pre-dispatch replay, academy, life-record, and RAG prompt tests keep passing.

## Domain Model
- `PreDispatchCandidate`: plugin-provided action, route, intent, confidence, evidence, and optional required tool.
- `DecisionTwinProfile`: memory-backed routing policy that prefers tool-grounded candidates and records source evidence.
- `LlmRouteDecision`: LLM-produced JSON intent decision with `action`, `route`, `intent`, `required_tool`, `confidence`, and `evidence`.
- `PreDispatchDecision`: selected action plus policy trace fields.

## API Contract
No external API changes. `resolve_pre_gateway_dispatch()` remains backward compatible; tests may pass an explicit profile.

## UI Contract
No frontend surface change. Discord-visible errors remain Korean plain-language replies through existing gateway sanitizers.

## Test Plan
- Unit: candidate ranking prefers required-tool candidates over generic responses.
- Unit: policy trace fields are populated.
- Prompt: workspace prompt includes decision-twin routing instructions.
- Regression: existing pre-dispatch replay and RAG prompt tests.

## Implementation Tasks
- [ ] T1: Add failing tests for tool-first decision policy.
  - Files: `tests/gateway/test_pre_gateway_dispatch_decision.py`
  - Acceptance: current resolver fails before implementation.
- [x] T2: Add decision-twin policy module and integrate it into resolver.
  - Files: `gateway/decision_twin.py`, `gateway/pre_dispatch.py`
  - Acceptance: focused routing tests pass.
- [x] T3: Add decision-twin instructions to Discord workspace prompt.
  - Files: `gateway/discord_workspace_prompt.py`, `tests/gateway/test_discord_workspace_prompt.py`
  - Acceptance: prompt test passes.
- [x] T4: Add LLM-backed decision twin plugin.
  - Files: `plugins/decision_twin/`, `tests/plugins/test_decision_twin_plugin.py`
  - Acceptance: authorized turns can be rewritten from LLM JSON; unauthorized turns skip the judge.
- [ ] T5: Run wider regression checks and commit.
  - Files: test/lint only.
  - Acceptance: focused routing/RAG tests and lint pass.

## Risks
- LLM judge failures must fail open to normal dispatch so the gateway does not block messages during provider outages.
- Tool metadata quality matters; weak plugin evidence should be improved in the plugin rather than patched with central keyword rules.
