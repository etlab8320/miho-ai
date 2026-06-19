# Agent Reach Miho Adapter Spec

## Problem
Miho needs better routing for web, YouTube, GitHub, RSS, and social research
requests without replacing its existing tools or changing provider behavior.

## Scope
### In
- Report the local Agent Reach CLI status and doctor channel map.
- Route a natural-language request to Agent Reach channels with backend status.
- Provide command examples only; do not execute platform read/write actions.

### Out
- Browser cookie import, login setup, package installation, service restart.
- Replacing Miho's existing `web_search` or `web_extract` tools.
- Any write action on external platforms.

## Acceptance Criteria
- Miho auto-discovers the new toolset through `tools.registry`.
- Missing Agent Reach CLI returns a safe structured status, not an exception.
- Doctor JSON from Agent Reach is normalized for current top-level channel output.
- YouTube and GitHub prompts route to the correct channel.
- Tests cover missing CLI, doctor normalization, routing, and registry discovery.

## Test Plan
- Add focused pytest coverage in `tests/tools/test_agent_reach_tool.py`.
- Run the canonical test runner for the focused test file.
- Run a registry smoke check through `model_tools.get_tool_definitions`.
