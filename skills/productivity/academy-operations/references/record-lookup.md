# Peak record lookup notes

Use this when 맥스 asks for a specific event's records for today, e.g. `오늘 제자리멀리뛰기 기록 보여달라`, `오늘 20m 왕복달리기`, or `이번주 배근력`. This is a read-only leaderboard/summary request, not a single-student card request.

## Preferred decision tree

1. If the user names a student, use the student-card / student-detail path instead of a leaderboard.
2. If the user asks for today's event records and there is a dedicated ranking endpoint, use it first.
3. If no event-specific leaderboard is exposed, fan out across active Peak students and aggregate `GET /peak/records?student_id=...`.
4. Match records by exact event name (`record_type_name` / `event_name`) and exact measurement date.
5. Sort by event semantics:
   - distance / height / score events: descending
   - time / seconds events: ascending
   - repetition events: usually descending, but prefer the event's own ranking rule if the API provides one

## Practical notes

- Do not mix different events that share an id; prefer exact name matching.
- Keep the response compact: date, event, total count, then names with school/grade/value/unit.
- Avoid leaking unnecessary student fields.
- If the lookup is for `오늘`, use the current system date, not the message timestamp.

## Example API pattern

```python
from datetime import date
from plugins.academy_ops.auth_store import load_bindings, decrypt_token
from plugins.academy_ops.paca_client import DEFAULT_PACA_BASE_URL
from plugins.academy_ops.academy_api import AcademyApiClient

binding = next(iter(load_bindings().values()))
token = decrypt_token(binding.token_ciphertext) or ""
client = AcademyApiClient(token=token, base_url=DEFAULT_PACA_BASE_URL)

today = date.today()
rows = []
for student in client.list_peak_students():
    peak_id = student.get("peak_student_id") or student.get("id")
    if not peak_id:
        continue
    for record in client.list_peak_records(int(peak_id)):
        if (record.get("record_type_name") or record.get("event_name")) == "제자리멀리뛰기" \
           and (record.get("measured_at") or record.get("date")) == today.isoformat():
            rows.append(record)
```

This pattern is especially useful when the tool surface has student-level record reads but no dedicated event leaderboard endpoint.