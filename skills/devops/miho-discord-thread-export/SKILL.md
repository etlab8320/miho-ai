---
name: miho-discord-thread-export
description: Use when a user wants data stored in a Miho-managed Discord thread exported into Excel/CSV-style deliverables, or when you need to turn thread history into a structured logbook.
version: 1.0.0
author: Miho Agent
license: MIT
metadata:
  miho:
    tags: [discord, thread, export, excel, xlsx, miho, workspace, logs]
    related_skills: [miho-discord-workspaces, miho-discord-kanban-workspaces]
---

# Miho Discord Thread Export

## Overview

Miho-managed Discord threads keep durable local storage under `~/.miho/discord/...`, including raw thread metadata and RAG message history. When a user asks for an export — especially an Excel workbook they can inspect, share, or continue editing — the fastest reliable path is to read the thread storage directly and build a structured workbook from that local data.

This skill is for **data extraction and packaging**, not for general Discord conversation. It covers how to locate the thread on disk, which files matter, how to design a useful workbook, and how to avoid overpromising structure that does not actually exist in the stored data.

## When to Use

Use this skill when:
- A user asks to export a Discord thread to Excel, CSV, Sheets-ready tables, or a structured report.
- You need to summarize a Miho Discord thread into multiple tabs such as summary, raw messages, and derived logs.
- A thread is being used as an operational logbook: health, student tracking, issue triage, planning, QA notes, or daily check-ins.

Do not use this skill for:
- General Discord messaging that does not need filesystem-backed export.
- Full analytics over all guilds/channels unless the user asked for cross-thread reporting.
- Situations where the user only wants a quick in-chat summary and no file output.

## Storage Layout to Inspect

Typical Miho Discord thread workspace layout:

```text
~/.miho/discord/guilds/<guild_id>/channels/<channel_prefix>___<channel_id>/threads/thread__<thread_id>/
  thread.json
  context.md
  rag/
    messages.jsonl
    index.json
    vector_index.json
    vectors.jsonl
```

Key files:
- `thread.json` — thread metadata such as thread id, name, created/updated timestamps.
- `rag/messages.jsonl` — raw conversation history with timestamp, role, user_name, message_id, and text.
- `context.md` — useful if you need thread-scoped context, but not mandatory for basic export.

See `references/storage-layout-and-workbook-pattern.md` for a compact field-level reference and workbook pattern.

## Core Workflow

1. **Identify the thread directory exactly.**
   - Prefer the active thread path if already known from the session or thread-scoped workspace.
   - Confirm the presence of `thread.json` and `rag/messages.jsonl` before building anything.

2. **Read metadata first.**
   - Use `thread.json` to capture thread name, thread id, created_at, updated_at.
   - This metadata should appear in the workbook's first sheet.

3. **Read raw messages without inventing schema.**
   - `messages.jsonl` is the authoritative source.
   - Export raw rows into a dedicated sheet like `대화원본` or `raw_messages`.
   - Preserve timestamp, role, user_name, message_id, and text.

4. **Derive structure only when evidence exists.**
   - If the conversation clearly contains structured facts (for example height/weight/medication or dated meals), create additional sheets for those.
   - When parsing, be explicit that these sheets are derived from message content.
   - Avoid pretending to have richer DB fields than what the thread actually stores.

5. **Design the workbook for human use, not just data dump.**
   Recommended tabs:
   - `요약` — thread metadata + high-level extracted facts
   - `대화원본` — every stored message row
   - one or more derived tabs such as `식사기록`, `체중기록`, `운동기록`, `복약기록`

6. **Style lightly, verify concretely.**
   - Freeze header row.
   - Apply wrap text to message columns.
   - Widen columns enough to be usable.
   - Reopen the workbook after writing and verify sheet names, row counts, and a few key cells.

## Workbook Design Patterns

### Minimum viable export

Use this shape when the user just wants the data out quickly:
- `요약`: thread info, export timestamp, message count
- `대화원본`: raw message table

### Operational logbook export

Use this shape when the thread acts like a tracker:
- `요약`: baseline profile and thread status
- `대화원본`: full audit trail
- derived tabs by domain:
  - health: meals, weight, sleep, medication, supplements, symptoms
  - operations: tasks, decisions, blockers, follow-ups
  - academy/student: attendance events, counseling notes, action items

### Evidence-first parsing rule

If there are only a few explicit structured facts, extract only those. Do not create empty pseudo-database tabs just because the user mentioned “DB”. A faithful partial workbook beats a fake comprehensive one.

## Parsing Heuristics

- Prefer **user-authored lines** as the source of truth for factual logs.
- Assistant messages are acceptable as normalization targets if they restate the user's data clearly and losslessly.
- For repeated time-based entries, convert into one row per event.
- Keep original phrasing available in the raw sheet even when you create normalized tabs.
- If timing is ambiguous (`점심쯤`, `아까`, `월요일쯤`), preserve the original wording instead of inventing exact timestamps.

## Health-Log Specific Guidance

When the thread is a personal health log:
- Treat the thread itself as the primary running journal.
- Keep long-lived baseline facts separate in `요약` rather than forcing everything into profile logic.
- Good derived tabs include:
  - `식사기록`
  - `체중기록`
  - `수면컨디션`
  - `복약/영양제`
- If only one category has enough data so far, ship that one cleanly rather than generating four mostly empty tabs.

## Common Pitfalls

1. **Confusing thread-local logs with durable profile facts.**
   A user may consider the thread itself the real record. Export the thread faithfully first; profile abstractions are secondary.

2. **Exporting only a summary and omitting raw messages.**
   Users often want auditability. Always include a raw-message sheet unless the user explicitly asked not to.

3. **Assuming a relational schema exists.**
   The local Discord workspace is often JSON/JSONL-backed, not a normalized database.

4. **Not reopening the workbook after writing.**
   A generated `.xlsx` is not verified until you load it again and inspect basic structure.

5. **Over-parsing vague language.**
   Preserve ambiguity instead of fabricating precision.

## Verification Checklist

- [ ] Located the correct thread directory under `~/.miho/discord/.../threads/thread__<thread_id>/`
- [ ] Confirmed `thread.json` and `rag/messages.jsonl` exist
- [ ] Exported a raw-message sheet with timestamp, role, user_name, message_id, text
- [ ] Added a summary sheet with thread metadata and export timestamp
- [ ] Added derived sheets only for facts clearly supported by the messages
- [ ] Reopened the workbook and confirmed sheet names and representative cells
- [ ] Delivered the actual file path or media attachment back to the user

## One-Shot Recipes

### Export one thread to Excel

1. Read `thread.json`
2. Read `rag/messages.jsonl`
3. Build workbook with `요약` + `대화원본`
4. Add domain-specific tabs if the content is structured enough
5. Save under a shareable path like `~/.miho/media_cache/<descriptive-name>.xlsx`
6. Reopen the workbook to verify before sending

### Export a health thread quickly

1. Put baseline metrics in `요약`
2. Put the full transcript in `대화원본`
3. Extract explicit meal rows into `식사기록`
4. Leave weight/sleep/medication tabs for later if the data is not present yet
5. Send the workbook and explain briefly what is included now vs later as more logs accumulate
