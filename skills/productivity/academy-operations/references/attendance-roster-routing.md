# Attendance vs class roster routing (session note)

Use this routing when the user asks for today's students.

## Rule

- **"오늘 출석해야 할 학생들 / 오늘 출석할 학생 명단"** → use **`class_roster_range`** with today's date and `with_roster=true`.
- **`academy_attendance_day`** is for **actual attendance status** (present / late / absent / unknown) after the day is being tracked.
- **`academy_schedule_range`** is for **academy_events** (events / holiday / office items), not class rosters.

## Why this matters

In the verified flow from this session:

1. `academy_attendance_day` for `2026-05-31` returned all-zero attendance.
2. `academy_class_roster_range` for the same date returned the real class roster: one afternoon class with 10 enrolled students.

So, if the user is asking who should attend today, do **not** infer the answer from attendance counts alone.

## Output preference

- Keep the reply concise.
- If the user wants an image, render a simple, high-legibility card with date, class slot, and names.
- Avoid mixing event schedules with class attendance.
