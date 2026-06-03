# Subscription/OAuth-capable Miho Provider Map — 2026-05 session notes

These notes came from a provider-strategy discussion with Max. They are not a live capability guarantee; verify with `miho model`, provider docs, and the account’s actual entitlements before configuring.

## Strong default for Max

**Keep OpenAI Codex as Miho’s main provider** when the task is agentic development: coding, debugging, repo edits, SSH/server work, and long tool loops. The subscription-backed comfort and tool-loop reliability matter more than raw leaderboard position.

## Practical roles

| Provider path | Practical role | Strength | Caveat |
|---|---|---|---|
| OpenAI Codex / ChatGPT subscription | Main Miho brain for development | Agentic coding, tool loops, persistence | Account limits and OAuth state still matter |
| Google Gemini OAuth / Code Assist | Specialist for Google/workspace/multimodal | Drive/Docs/Sheets-style work, long docs, images/video | Less ideal as sole coding executor |
| GitHub Copilot / Copilot ACP | Coding assistant + possible Claude/Gemini access | IDE/coding integration, model variety | GitHub controls routing, limits, model exposure |
| Nous Portal | Aggregator/specialist access to many models, including possible Claude slugs | Claude/GPT/Gemini/Kimi-style optional access from one provider | Not a clean unlimited Claude subscription replacement; usage may be token/credit/plan limited |
| xAI OAuth / SuperGrok | Research/conversational specialist | Fast, current-info style exploration | Long coding consistency may lag Codex/Claude |
| Qwen OAuth | Secondary coding/math/open-model specialist | Good code/math value | Regional/account model exposure can vary |
| Kimi Coding Plan | Long-context/code-reading specialist | Useful for long code/document reading | Verify global vs China account behavior |
| MiniMax OAuth / Token Plan | Experimental coding/agent plan, including MiniMax M3 when exposed by the account/catalog | Can be plugged as an OAuth-style specialist; MiniMax Token Plan is subscription-style and shares usage credits across Agent/API-style usage | Less proven as main brain; Miho's curated fallback list may lag newest MiniMax model releases, so verify `miho model`, models.dev, and actual account entitlement before making it default |
| OpenCode Go / Ollama Cloud | Cheap auxiliary/open-model route | Low-cost summaries, local/open model experiments | Not ideal for highest-stakes agentic reasoning |

## Nous + Claude caveat

Say this precisely:

> Nous can expose Claude models through its portal/aggregator route, but it is not the same as attaching an Anthropic consumer subscription directly to Miho. Treat it as a paid/limited specialist route, not an unlimited Claude engine.

## Recommended architecture phrasing

Use this concise framing with Max:

```text
Codex = hand / executor / king
Gemini = eye / Google + document + multimodal specialist
Claude = reviewer / architect / critic
Qwen-Kimi-MiniMax = cheap workers / batch helpers
Grok = fast scout / research chatter
```

## Implementation idea

Build toward a router, but keep one final executor:

1. Default main provider remains Codex.
2. Specialist calls are selected by task class.
3. Specialist output returns to Codex.
4. Codex decides final answer/actions.

Avoid splitting final authority across multiple models unless a deterministic arbiter exists.
