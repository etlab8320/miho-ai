# Storage layout and workbook pattern

## Observed Miho Discord thread layout

Typical path:

```text
~/.miho/discord/guilds/<guild_id>/channels/<channel_prefix>___<channel_id>/threads/thread__<thread_id>/
```

Common files:
- `thread.json`
  - `guild_id`
  - `parent_channel_id`
  - `thread_id`
  - `thread_name`
  - `created_at`
  - `updated_at`
- `rag/messages.jsonl`
  - one JSON object per message
  - common keys: `timestamp`, `message_id`, `user_id`, `user_name`, `role`, `text`
- `context.md`
  - optional thread context note

## Recommended Excel workbook shape

### Sheet 1: 요약
Columns:
- `항목`
- `값`

Suggested rows:
- thread name
- thread id
- created_at
- updated_at
- export timestamp
- message count
- domain-specific baseline facts

### Sheet 2: 대화원본
Columns:
- `timestamp`
- `role`
- `user_name`
- `message_id`
- `text`

### Derived sheets
Only add these when the messages support them clearly.

Examples:
- `식사기록`: `date`, `time`, `item`, `source`
- `체중기록`: `date`, `weight_kg`, `source`
- `복약기록`: `date`, `time_or_note`, `medication`, `dose`, `source`
- `운동기록`: `date`, `activity`, `duration`, `intensity`, `source`

## Health-thread example from session

The workbook that worked well in this session used:
- `요약`
- `대화원본`
- `식사기록`

Why this was the right scope:
- baseline profile facts were explicit (height, weight, Mounjaro, supplements)
- meal entries were explicit enough to normalize into rows
- other domains like sleep/exercise did not yet have enough records, so empty tabs would have added noise

## Export principle

When a user says “DB를 엑셀로”, interpret that as **“turn the stored thread data into a useful workbook”**, not as a promise that the source is a formal SQL-style database.
