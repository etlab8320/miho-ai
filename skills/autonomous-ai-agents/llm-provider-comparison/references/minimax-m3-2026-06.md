# MiniMax M3 comparison notes — 2026-06 session snapshot

Context: User asked whether MiniMax M3 is better than GPT-5.5 for coding and whether the price is “crazy cheap.” Verified against official MiniMax docs and pricing pages rather than marketing blurbs.

## Verified public claims

- MiniMax homepage positions M3 as:
  - “Coding 顶尖”
  - “1M 上下文”
  - “原生多模态”
- MiniMax docs describe M3 as strong in:
  - code understanding
  - multi-turn dialogue
  - reasoning
  - agentic tool use / interleaved thinking
- MiniMax docs provide Anthropic-compatible setup instructions for Claude Code and explicitly state that API key choice determines billing mode.

## Pricing snapshot observed in docs

### Token Plan

- Plus: $20/month
- Max: $50/month
- Ultra: $120/month
- Shared monthly quota across supported resources.

### Pay as You Go

MiniMax-M3 paygo pricing shown in docs:

- ≤512k input tokens: 50% off promo, then
  - Input: $0.30 / 1M tokens
  - Output: $1.20 / 1M tokens
  - Prompt caching read: $0.06 / 1M tokens
- >512k input tokens:
  - Input: $1.20 / 1M tokens
  - Output: $4.80 / 1M tokens
  - Prompt caching read: $0.24 / 1M tokens

Priority tier pricing is also listed, but should be treated as a separate higher-cost path.

## Practical interpretation

- The “cheap” claim is plausible on token economics.
- The “better than GPT-5.5” claim is still marketing until verified by hands-on tasks:
  - repo-sized code comprehension
  - multi-file editing
  - test-fix loops
  - long agent runs
- For comparison answers, separate:
  1. marketing claim,
  2. official capability docs,
  3. actual price sheet,
  4. empirical coding benchmark from the user’s repo.

## Source paths used in session

- `https://minimaxi.com/`
- `https://platform.minimax.io/docs/llms.txt`
- `https://platform.minimax.io/docs/guides/text-ai-coding-tools.md`
- `https://platform.minimax.io/docs/guides/pricing-token-plan.md`
- `https://platform.minimax.io/docs/guides/pricing-paygo.md`
