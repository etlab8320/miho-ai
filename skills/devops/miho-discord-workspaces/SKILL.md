---
name: miho-discord-workspaces
description: Operate Miho Discord channel/thread workspaces with scoped RAG, vector memory, gateway verification, and safe Kanban linkage.
version: 1.0.0
platforms: [linux, macos, windows]
metadata:
  miho:
    tags: [miho, discord, gateway, rag, vector-search, workspace]
    related_skills: [miho-agent, miho-discord-kanban-workspaces]
---

# Miho Discord Workspaces

Use this skill when working with Miho's Discord gateway workspace model: channel/thread folders under `~/.miho/discord/`, RAG memory, vector retrieval, context injection, or workspace archive behavior.

## Core model

Miho keeps Discord memory in local install state, not in the repo:

```text
~/.miho/discord/guilds/<guild_id>/
└── channels/
    └── <channel_slug>__<channel_id>/
        ├── channel.json
        ├── context.md
        ├── rag/
        │   ├── index.json
        │   ├── messages.jsonl
        │   └── vectors.jsonl
        └── threads/
            └── <thread_slug>__<thread_id>/
                ├── thread.json
                ├── context.md
                └── rag/
                    ├── index.json
                    ├── messages.jsonl
                    └── vectors.jsonl
```

## Semantics

- Channel folders hold channel-level context and rollups.
- Thread folders hold only that thread's local memory.
- A thread may write summary events to the parent channel, but thread prompt context must not leak sibling thread messages.
- Deleting a Discord channel or thread archives its workspace instead of deleting memory.
- Vector memory is local by default. Voyage/OpenAI embeddings may be configured, but local hash fallback must keep memory usable without external services.

## Useful commands

In Discord:

```text
/memory status
/memory search 로그인 방식
/memory rebuild
```

In terminal:

```bash
miho setup tools
miho gateway status
miho logs --follow --level info
```

## Operational checklist

When auditing or changing Discord workspace behavior, verify the full chain rather than only the code diff:

1. Confirm repo state and recent commits:
   ```bash
   git status --short
   git log --oneline -8
   ```
2. Confirm Miho runtime and gateway service:
   ```bash
   miho --version
   miho gateway status
   ```
   A healthy macOS launchd install should say the service definition matches the current Miho install and show the running `python -m miho_cli.main gateway run --replace` command. If it reports stale service definition, run `miho gateway start` and re-check before declaring it fixed.
3. Inspect the target workspace on disk:
   - `channel.json` / `thread.json`
   - `context.md`
   - `rag/index.json`
   - `rag/messages.jsonl`
   - `rag/vector_index.json` and `rag/vectors.jsonl` when vector memory is enabled
4. Check the `index.json` counters (`message_count`, `vector_count`, `embedding_method`) match the expected behavior.
5. If assistant responses are part of memory, verify `record_assistant_turn` is wired through the gateway final-response path, not only inbound user messages.

## Verification

After changing workspace code:

```bash
./scripts/run_tests.sh \
  tests/gateway/test_discord_workspace.py \
  tests/gateway/test_discord_workspace_vectors.py \
  tests/gateway/test_discord_memory_ops.py
```

For focused checks during iteration:

```bash
./.venv/bin/python -m pytest \
  tests/gateway/test_discord_workspace.py \
  tests/gateway/test_discord_workspace_vectors.py -q
```

Then verify the gateway service:

```bash
miho gateway status
```
