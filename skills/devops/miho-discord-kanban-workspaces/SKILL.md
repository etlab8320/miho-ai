---
name: miho-discord-kanban-workspaces
description: Configure selected Miho Discord channels and threads with scoped Kanban boards while keeping RAG as the memory layer.
version: 1.0.0
platforms: [linux, macos, windows]
metadata:
  miho:
    tags: [miho, discord, kanban, gateway, workspace]
    related_skills: [miho-discord-workspaces, kanban-orchestrator, kanban-worker]
---

# Miho Discord Kanban Workspaces

Use this skill when a selected Discord channel should become a work board. Do not turn every Discord channel into Kanban by default.

## Rule

- RAG is memory/context.
- Kanban is execution/status.
- Channel Kanban is the large map: backlog, priorities, release candidates, and thread index.
- Thread Kanban is the small workbench: implementation steps, bug investigation, tests, review, blocked items, and done summaries.
- Prefer one board per stable work channel, with channel/thread metadata (`kanban.json`) binding the Discord workspace to board scope. Do not create a separate SQLite board for every thread unless the user explicitly asks.
- For non-work channels, leave Kanban unbound. RAG can remain automatic while Kanban is opt-in.

## Recommended setup

Create one board per stable work channel:

```bash
miho kanban boards create discord-coding \
  --name '#00_코딩' \
  --description 'Discord coding channel work board. Channel is the large map; threads are workbenches.'
```

Write channel and thread metadata in the Discord workspace:

Channel `kanban.json`:

```json
{
  "version": 1,
  "kind": "miho-discord-channel-kanban",
  "enabled": true,
  "board": "discord-coding",
  "scope": "channel",
  "role": "large-kanban-map"
}
```

Thread `kanban.json`:

```json
{
  "version": 1,
  "kind": "miho-discord-thread-kanban",
  "enabled": true,
  "board": "discord-coding",
  "scope": "thread",
  "role": "small-kanban-workbench",
  "parent_channel_kanban": "<channel-workspace>/kanban.json"
}
```

Also write the operating policy into the channel/thread `context.md` so future runs know the intended split: channel board = big map, thread board = workbench, RAG = memory, Kanban = execution.

## Usage

In the target Discord channel or thread:

```text
/kanban --board discord-coding create "Fix Miho setup UX"
/kanban --board discord-coding list
/kanban --board discord-coding show <task_id>
```

For general users and non-work channels, leave Kanban unbound. The default installation keeps the dispatcher available but does not automatically attach boards to arbitrary Discord channels.

## Verification

```bash
miho kanban boards list
miho kanban --board discord-coding stats
miho gateway status
```
