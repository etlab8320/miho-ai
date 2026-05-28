---
name: product-ui-design
description: Production UI design router for Miho skills.
version: 1.0.0
author: Miho Agent
license: MIT
platforms: [linux, macos, windows]
tags: [design, ui, ux, html, frontend, production, accessibility, responsive]
related_skills: [claude-design, sketch, popular-web-designs, design-md, dogfood]
---

# Product UI Design

Use this skill when Miho is asked to design, redesign, review, or implement
product UI that may ship in an existing app. It acts as the production router
for Miho's creative design skills and adds quality gates before the work is
reported done.

## When To Use

Use this skill for:

- Existing project screens, app shells, dashboards, settings, forms, onboarding,
  admin tools, editor surfaces, and multi-step workflows.
- Product UI reviews where the user asks what is stronger, weaker, confusing,
  risky, or production-ready.
- HTML or frontend prototypes that should respect an app's real constraints,
  not just look good in isolation.
- Visual polish passes where responsive behavior, error states, loading states,
  empty states, accessibility, and console health matter.

Do not use this skill for standalone illustrations, diagrams, videos, or
purely decorative assets unless they are part of a product interface.

## Routing

Start here, then use the narrowest supporting skill that fits the task.

| Need | Route |
| --- | --- |
| Production app UI or code-backed screen | Use this skill as the controller. Inspect the existing project first. |
| One-off visual artifact or rich HTML exploration | Use `claude-design`, then apply this skill's production gates if it may ship. |
| Two or three alternate visual directions | Use `sketch` to branch options, then choose one direction with this skill. |
| Familiar style vocabulary or benchmark patterns | Use `popular-web-designs` as a reference library, not the source of truth. |
| Durable design spec, tokens, or component rules | Use `design-md` after the implementation direction is clear. |
| Usability validation against Miho behavior | Use `dogfood` after the first working screen exists. |

## Production Workflow

1. Identify whether the task is for an existing project or a new isolated
   artifact. For an existing project, read local instructions such as
   `AGENTS.md`, `CLAUDE.md`, `README`, `DESIGN.md`, route files, global CSS,
   component folders, and existing tests before changing UI.
2. Define the real user workflow in one sentence: user, job, primary action,
   and success state.
3. Reuse the app's established stack, components, typography, spacing, tokens,
   icons, form patterns, data loading patterns, and error handling.
4. Choose supporting Miho design skills only for the missing part: exploration,
   reference, specification, or critique.
5. Implement the smallest cohesive UI change that completes the workflow.
6. Verify with browser-facing checks before reporting done.

## Design Rules

- Treat the existing project as the highest priority source. A template is
  only supporting material.
- Use `popular-web-designs` as a reference library, not the source of truth.
- Do not copy distinctive proprietary layouts, brand assets, illustrations, or
  paid product screens. Borrow general interaction patterns only.
- Do not invent fake metrics, fake testimonials, fake customer names, fake
  analytics, or fake production data. Use placeholders that are clearly labels
  or wireframe data when real data is unavailable.
- Prefer dense, scannable, task-focused UI for operational tools. Avoid
  marketing hero layouts inside product workflows.
- Keep page sections unframed unless the app already uses framed panels for
  that surface. Do not put cards inside cards.
- Icons should come from the project's existing icon system when available.
- On-screen copy should be plain language. User-facing errors must not expose
  stack traces, HTTP codes, CORS terms, implementation details, or coding terms.
- Korean products should show Korean error messages and empty-state copy unless
  the project clearly uses another language.

## Required States

Every product UI change should account for:

- Default state with realistic content shape.
- Loading state that does not cause layout jumps.
- Empty state with a clear next action when one exists.
- Error states with plain-language recovery guidance.
- Disabled or permission-limited state when the action can be unavailable.
- Responsive layouts for mobile and desktop widths.
- Keyboard navigation for interactive controls.
- Accessibility basics: semantic controls, labels, visible focus, contrast, and
  non-color-only status indicators.

## Verification Gates

Before reporting the result as complete, run the checks that match the project:

- Unit or component tests for changed logic and user-facing states.
- Integration or browser smoke path for the primary workflow.
- Responsive viewport checks for at least one mobile and one desktop width.
- Browser console check for errors and hydration warnings.
- Accessibility pass for labels, focus order, keyboard use, and contrast.
- Screenshot or visual review when the task is mostly visual.
- Build, lint, and type-check when frontend code changed.

If a check is skipped, state the concrete reason. Do not call work production
ready when responsive behavior, console errors, error states, or accessibility
were not considered.

## Output Style

When reporting design work, be direct:

- Name the route used and any supporting skills consulted.
- List the changed files or artifact paths.
- Summarize verification commands and results.
- Call out remaining risk only when it is actionable.
