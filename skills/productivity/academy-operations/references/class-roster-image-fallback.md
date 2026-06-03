# Class roster image fallback

Use this when the user asks for a future/planned class roster as an image (예: `다음주 목요일 출석해야할 학생명단 이미지로 줘`) and the public `academy_class_roster_range` wrapper only returns JSON/text or rejects an `image` argument.

## Verified pattern

1. Resolve the relative weekday to an explicit `YYYY-MM-DD` using the live system date.
2. Fetch planned roster data from PACA class schedules, not attendance check-ins:
   - `class_roster_for_range(client, target_day, target_day, with_roster=True)`
   - Use the stored academy binding/token for read-only fallback if the wrapper cannot infer Discord context.
3. Convert the roster to the attendance-day renderer's payload shape:
   - `date`: target date
   - `slots`: `{time_slot: [student rows...]}`
   - each student row should include `name`, `school`, `grade`, and `attendance_status="unknown"` when no check-in exists yet.
   - `summary`: `present=0`, `late=0`, `absent=0`, `unknown=<total roster students>`.
4. Render with `AttendanceDayRosterImageRenderer().render(payload)` and return exactly one `MEDIA:<path>` line.
5. Run visual QA before delivery: title/date visible, table not clipped, cards aligned.

## Minimal local script shape

```python
from datetime import date
from plugins.academy_ops.auth_store import load_bindings, decrypt_token
from plugins.academy_ops.paca_client import DEFAULT_PACA_BASE_URL
from plugins.academy_ops.academy_api import AcademyApiClient
from plugins.academy_ops.class_roster import class_roster_for_range
from plugins.academy_ops.attendance_day_renderer import AttendanceDayRosterImageRenderer

TARGET = date(YYYY, MM, DD)
binding = next(iter(load_bindings().values()))
token = decrypt_token(binding.token_ciphertext) or ""
client = AcademyApiClient(token=token, base_url=DEFAULT_PACA_BASE_URL)
roster = class_roster_for_range(client, TARGET, TARGET, with_roster=True)

slots = {}
for schedule in roster.get("schedules", []):
    slot = schedule.get("time_slot") or "unknown"
    for student in schedule.get("students") or []:
        row = dict(student)
        row["attendance_status"] = row.get("attendance_status") or "unknown"
        slots.setdefault(slot, []).append(row)

total = sum(len(rows) for rows in slots.values())
payload = {
    "date": TARGET.isoformat(),
    "summary": {"present": 0, "late": 0, "absent": 0, "unknown": total},
    "slots": slots,
}
image_path = AttendanceDayRosterImageRenderer().render(payload)
```

## Pitfall

Do not call `academy_class_roster_range` with empty args and then ask the user for a date when the relative weekday is clear. Resolve the date locally and retry/fallback. Also do not route future `출석해야 할` requests through `academy_attendance_day`; that is check-in status, not planned roster.
