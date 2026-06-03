---
name: miho-model-routing-strategy
description: "Plan and explain Miho multi-LLM/provider setups: Codex as main agent, Gemini/Claude/others as specialist routes, subscription/OAuth vs API-key tradeoffs, and model-routing decisions."
version: 1.0.0
author: Miho Agent
license: MIT
platforms: [macos, linux, windows]
metadata:
  miho:
    tags: [miho, providers, model-routing, codex, gemini, claude, oauth, subscription]
    related_skills: [miho-agent]
---

# Miho Model Routing Strategy

Use this skill when the user asks about which LLM/provider to use with Miho, subscription-based provider choices, OAuth/provider setup strategy, multi-model routing, or whether to make Miho use Codex/Gemini/Claude/Grok/Qwen/Kimi for different work.

This skill is advisory and architectural. For exact Miho commands, configuration mechanics, or troubleshooting Miho itself, also load `miho-agent` first.

## Core judgment pattern

Default recommendation for Max-style agentic development:

```text
Main responsible agent / execution loop → OpenAI Codex subscription
Vision / long docs / Google ecosystem → Gemini
Design critique / high-end reasoning review → Claude via Nous or GitHub Copilot when available
Cheap bulk summarization / secondary opinions → Qwen, Kimi, MiniMax, or similar
Fast research / conversational exploration → Grok/Gemini as optional specialists
```

Keep one final responsible model. Do **not** encourage a chaotic “every model answers at once” architecture unless there is a clear orchestration layer. For Miho, the safest pattern is:

```text
Codex = final executor and tool-using controller
Specialist models = scoped advisors or auxiliary workers
Codex = synthesizes and acts
```

## Subscription/OAuth vs API usage framing

When the user asks for “subscription” support, separate these cases clearly:

1. **True subscription/OAuth-style use** — e.g. OpenAI Codex/ChatGPT subscription route, Google Gemini OAuth/Code Assist, xAI OAuth/SuperGrok, Qwen OAuth, MiniMax OAuth, GitHub Copilot external process/OAuth-like flows.
2. **Aggregator subscription or credits** — e.g. Nous Portal can expose many models, but usage may still be token/credit metered and not feel like unlimited ChatGPT/Codex.
3. **Pure API key/pay-as-you-go** — exclude these when the user explicitly says to ignore API metered billing.

Pitfall: do not describe Nous/OpenRouter-style access as “Claude subscription replacement.” Say: it can expose Claude models, but usage limits/costs depend on the portal/account/model and may be unsuitable as a heavy main engine.

## Practical routing advice

### Codex as main Miho provider

Recommend Codex when the user needs:

- coding, debugging, refactoring, tests
- server work, SSH, deployment prep
- long tool loops
- Miho self-modification
- Discord/agentic workflows that require persistence and repeated correction

Reasoning: for agentic development, stability, tool-use loop quality, and subscription comfort often matter more than raw benchmark intelligence.

### Gemini as specialist route

Recommend Gemini as a strong specialist when the user mentions:

- Google Workspace: Gmail, Calendar, Drive, Docs, Sheets
- PDFs, admissions documents, long context, spreadsheets
- image/video/multimodal understanding
- document cleanup, counseling materials, academy operations data

Phrase it as: “Codex is the hand; Gemini is the eye.” Gemini can expand Miho’s Google/workflow reach without replacing Codex as the executor.

### Claude via Nous/Copilot

Recommend Claude for:

- architecture critique
- code review
- careful planning
- difficult reasoning checks

Caveat: Anthropic consumer subscriptions usually do not map cleanly to Miho as a direct provider. Claude may be reachable through Nous/OpenRouter-like portals or GitHub Copilot model access, but those are not the same as attaching the Anthropic app subscription directly.

## Suggested phased implementation

### Phase 1 — Manual switching

Use Miho’s model picker/`/model` flow to switch provider/model per session when needed. Lowest risk; user chooses explicitly.

### Phase 2 — Auxiliary specialization

Keep Codex as `model.provider`, then configure or implement auxiliary calls for vision, document extraction, compression/summarization, or research where Gemini or cheaper models make sense.

### Phase 3 — Intent router

Add an intent classifier/router that maps tasks to specialist models:

```text
coding/debug/server → Codex
PDF/image/long document/google workspace → Gemini
architecture/code review → Claude via Nous/Copilot
cheap batch summary → Qwen/Kimi/MiniMax
fast research/exploration → Grok/Gemini
```

Then return the specialist result to Codex for final decision and execution.

## Response style for this user

When advising Max about provider choices:

- Lead with a blunt conclusion.
- Distinguish “possible” from “worth making the default.”
- Use concrete role labels: main engine, eye, reviewer, cheap worker.
- Mention usage-limit risk for aggregator/credit providers.
- Avoid overstating any provider as unlimited unless verified.
- If asked for a visual summary, create a readable image/table and verify legibility before sending.

## References

- `references/subscription-provider-map-2026-05.md` — session-derived map of subscription/OAuth-capable Miho provider options and their practical roles.
