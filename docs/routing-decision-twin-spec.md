# Miho Routing Decision Twin Spec

## Problem
Miho can still answer from a generic route when a turn has enough context to use a dedicated tool. Owner rules and prior corrections must influence routing without brittle keyword checks.

## Users And Jobs
ET needs Miho to infer the current job from the user text, thread context, owner memory, and plugin evidence, then call the right tool before producing a user-visible answer.

## Scope
### In
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
- The decision object records the decision-twin policy state and memory evidence.
- Discord workspace prompts tell Miho to infer intent from current text, thread memory, and owner profile before answering.
- Existing pre-dispatch replay, academy, life-record, and RAG prompt tests keep passing.

## Domain Model
- `PreDispatchCandidate`: plugin-provided action, route, intent, confidence, evidence, and optional required tool.
- `DecisionTwinProfile`: memory-backed routing policy that prefers tool-grounded candidates and records source evidence.
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
- [ ] T2: Add decision-twin policy module and integrate it into resolver.
  - Files: `gateway/decision_twin.py`, `gateway/pre_dispatch.py`
  - Acceptance: focused routing tests pass.
- [ ] T3: Add decision-twin instructions to Discord workspace prompt.
  - Files: `gateway/discord_workspace_prompt.py`, `tests/gateway/test_discord_workspace_prompt.py`
  - Acceptance: prompt test passes.
- [ ] T4: Run wider regression checks and commit.
  - Files: test/lint only.
  - Acceptance: focused routing/RAG tests and lint pass.

## Risks
- If no plugin emits a tool candidate, the central selector cannot invent one deterministically. The workspace prompt reduces this gap by forcing the agent to make a tool-use decision before answering.
- Tool metadata quality matters; weak plugin evidence should be improved in the plugin rather than patched with central keyword rules.
