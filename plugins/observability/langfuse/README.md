# Langfuse Observability Plugin

This plugin ships bundled with Miho but is **opt-in** — it only loads when
you explicitly enable it.

## Enable

```bash
pip install langfuse
miho plugins enable observability/langfuse
```

Or check the box in the interactive `miho plugins` UI.

## Required credentials

Set these in `~/.miho/.env`:

```bash
MIHO_LANGFUSE_PUBLIC_KEY=pk-lf-...
MIHO_LANGFUSE_SECRET_KEY=sk-lf-...
MIHO_LANGFUSE_BASE_URL=https://cloud.langfuse.com   # or your self-hosted URL
```

Without the SDK or credentials the hooks no-op silently — the plugin fails
open.

## Verify

```bash
miho plugins list                 # observability/langfuse should show "enabled"
miho chat -q "hello"              # then check Langfuse for a "Miho turn" trace
```

## Optional tuning

```bash
MIHO_LANGFUSE_ENV=production       # environment tag
MIHO_LANGFUSE_RELEASE=v1.0.0       # release tag
MIHO_LANGFUSE_SAMPLE_RATE=0.5      # sample 50% of traces
MIHO_LANGFUSE_MAX_CHARS=12000      # max chars per field (default: 12000)
MIHO_LANGFUSE_DEBUG=true           # verbose plugin logging
```

## Disable

```bash
miho plugins disable observability/langfuse
```
