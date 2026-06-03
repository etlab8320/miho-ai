---
name: llm-provider-comparison
description: Compare LLM/provider options for agentic development, especially subscription/OAuth-based Miho provider choices, and produce concise Korean decision artifacts or infographics.
version: 1.0.0
author: Miho Agent
license: MIT
platforms: [macos, linux]
metadata:
  miho:
    tags: [llm, providers, subscription, oauth, miho, comparison, infographic]
    related_skills: [miho-agent]
---

# LLM Provider Comparison

Use this skill when the user asks which LLM/provider/subscription to use for Miho, agentic coding, Claude/Codex/Gemini/Grok/Copilot comparisons, or wants a ranked table/image of model/provider options.

## Core principle

Separate **availability path** from **model intelligence**:

- API key / pay-as-you-go providers are different from subscription/OAuth providers.
- A model being announced does not mean it is available through the user's selected route.
- For Miho, verify the local provider names and model catalog before giving confident setup advice.
- For Korean users, lead with the cold practical recommendation, then show tradeoffs.

## Workflow

1. If the question concerns Miho configuration, load `miho-agent` first.
2. Verify the active Miho CLI/home when commands or local state matter:
   ```bash
   command -v miho || true
   miho --version || true
   ```
3. Inspect local Miho config/provider state when the user asks about their actual setup:
   - `~/.miho/config.yaml`
   - provider registry under `plugins/model-providers/`
   - model picker/catalog code if working inside the Miho repo.
4. Filter the answer by the user's constraint first. Example constraints:
   - subscription/OAuth only
   - no API pay-as-you-go
   - coding-agent use only
   - Korean-language UX
5. Rank for the user's actual job, not generic benchmark prestige. For Max-style agentic development, weight roughly:
   - tool-use reliability and long-running coding loops
   - code reasoning and debugging
   - context length / repository reading
   - model availability through the subscription path
   - Korean response quality
   - quota/entitlement stability
6. If the user asks whether a new model is “better than X,” separate the answer into:
   - vendor marketing claim
   - official capability docs
   - official pricing/billing docs
   - your practical verdict for the user's workload
7. Include both strengths and failure modes. Do not oversell a provider just because it has a top model.
8. If producing an image, generate a clean artifact and visually verify legibility before sending.

## Subscription/OAuth provider categories to check

Common Miho subscription-like routes may include:

- `openai-codex` — ChatGPT/Codex OAuth route; strong default for agentic coding.
- `nous` — Nous Portal subscription; useful for multi-model access.
- `google-gemini-cli` — Gemini OAuth / Code Assist route.
- `copilot` or `copilot-acp` — GitHub Copilot subscription routes; may expose GPT/Claude/Gemini variants depending on GitHub policy.
- `xai-oauth` — SuperGrok OAuth route.
- `qwen-oauth` — Qwen Portal login route.
- `kimi-coding` — Kimi Coding Plan / Moonshot route when available.
- `minimax-oauth` — MiniMax OAuth / coding-plan route.
- `opencode-go` / `ollama-cloud` style subscriptions where present.

Do **not** include direct API-key-only or pure pay-as-you-go options when the user explicitly excludes API billing.

## Infographic pattern

For Discord-friendly Korean comparison images:

1. Use a portrait canvas around 1800px wide for readability.
2. Keep columns simple: Rank, Provider/model, Strength, Caution, Score.
3. Use short Korean phrases; long caution text will collide with score bars.
4. Render SVG to PNG when possible; verify the PNG visually.
5. If text overlaps, shorten copy rather than shrinking fonts too much.
6. Attach with `MEDIA:/absolute/path/to/file`.

## Pitfalls

- Do not treat a provider marketing headline like “best for coding” as proof. Verify the official docs and pricing pages first, then decide whether the claim matters for the user's workload.
- Do not assume Anthropic consumer subscription can be directly used as a Miho provider. Distinguish Claude API, Claude Code, Copilot-mediated Claude, and portal/aggregator routes.
- Do not treat a provider catalog as permanent. Say that model exposure and quotas can change by account tier, region, and provider policy.
- Do not mix pay-as-you-go API options into a subscription-only answer unless explicitly labeled as excluded.
- Avoid overexplaining when the user asks for a practical buying/choice decision; give the verdict first.

## References

- `references/miho-subscription-provider-map-2026-05.md` — session-derived snapshot of subscription/OAuth provider ranking and infographic technique.
- `references/minimax-m3-2026-06.md` — official-doc snapshot for MiniMax M3 capability/price claims and how to separate marketing from real comparison.
