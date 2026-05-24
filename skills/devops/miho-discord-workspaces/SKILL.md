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

## Verification

After changing workspace code:

```bash
./scripts/run_tests.sh \
  tests/gateway/test_discord_workspace.py \
  tests/gateway/test_discord_workspace_vectors.py \
  tests/gateway/test_discord_memory_ops.py
```

Then verify the gateway service:

```bash
miho gateway status
```
