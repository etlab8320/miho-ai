# Governance Goal-First Routing Spec

## Problem

Miho sometimes routed a complex academy request by its surface artifact word
instead of the user's real job. Example: "look at last year's official PDF and
calculate this student's Daejin score with last year's formula" was treated as
PDF evidence gathering, not a previous-year Susi formula comparison.

## Scope

In:
- Preserve the original user text.
- Route previous-year Susi formula comparison to the Susi formula workflow.
- Keep PDF evidence as supporting source evidence, not the final calculator.
- Carry a success contract into the body agent rewrite.

Out:
- New hand-coded Korean intent parsers.
- Direct score calculation through terminal, sqlite, or arbitrary code.
- Replacing the existing LLM decision twin.

## Acceptance Criteria

- Previous-year official guide/formula comparison selects
  `susi_legacy_formula_compare`.
- The required workflow includes `susi26_rule_lookup`,
  `susi27_rule_lookup`, `susi27_score_calculate`, and source lookup.
- The rewrite tells the body agent what "done" means: old source evidence,
  student input, old calculation table, current calculation table, and the
  reason the scores differ.
- Decision twin prompt and contracts state that PDF wording does not override
  the formula-comparison goal.

## Test Plan

- Governance dispatcher routing tests.
- Decision twin prompt/contract tests.
- Domain pack and router map contract tests.
