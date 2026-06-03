# Miho subscription/OAuth provider map — 2026-05 session snapshot

Context: User asked which LLMs can be used with Miho through subscription-like routes only, excluding API pay-as-you-go billing, and wanted an image with practical intelligence ranking plus strengths/weaknesses.

## Local facts observed in session

- Active Miho config used `model.provider: openai-codex`, `base_url: https://chatgpt.com/backend-api/codex`, `default: gpt-5.5`.
- Miho provider picker/catalog included subscription/OAuth-style entries such as:
  - `openai-codex`
  - `xai-oauth`
  - `copilot`, `copilot-acp`
  - `google-gemini-cli`
  - `qwen-oauth`
  - `minimax-oauth`
  - `kimi-coding`
  - `ollama-cloud`
  - `opencode-go`
  - `nous`
- `anthropic` direct provider exists, but Anthropic consumer subscription should not be presented as a direct Miho subscription route. Treat Claude through Copilot/Nous/other allowed routes separately from Anthropic API billing.

## Practical ranking used for Max-style agentic development

1. OpenAI Codex — GPT-5.5 / GPT-5.3 Codex; strongest default for agentic coding/tool use; quota/account state can bite.
2. Nous Portal — multi-model subscription route with Claude/GPT/Gemini/Kimi-style access depending on policy; good backup/selector.
3. Google Gemini OAuth — excellent context/document/multimodal; long coding-agent stability can vary.
4. GitHub Copilot — coding-friendly and may expose Claude/GPT/Gemini through GitHub; routing/limits controlled by GitHub.
5. xAI Grok OAuth — fast/current/research-friendly; less consistent for long complex coding.
6. Kimi Coding Plan — strong long-context code reading/value; verify Korean/product stability.
7. Qwen OAuth Portal — strong coding/math/open ecosystem; regional/account exposure can differ.
8. MiniMax OAuth — can be attached through coding-plan/OAuth routes; less battle-tested vs top tier.
9. OpenCode Go / Ollama Cloud — useful as cheaper support routes; not ideal as main reasoning/coding brain.

## Infographic implementation notes

- SVG-to-PNG worked well for a Discord attachment.
- Use Apple SD Gothic Neo or another Korean-capable font.
- Initial image had score/caution text overlap; fix by shortening caution copy and moving the score above the bar.
- For readability, prefer a portrait 1800px-wide image and concise Korean phrases.

## Recommended final wording

Cold recommendation for this user:

- Main Miho brain: keep OpenAI Codex subscription.
- Best backup/alternative: Nous or GitHub Copilot, especially if Claude access matters.
- Experimental/support: Gemini, Grok, Qwen, Kimi, MiniMax.
- Always note that actual model exposure and quota depend on account tier, region, and provider policy.
