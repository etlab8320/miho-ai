# Weekly roster routing note

Session lesson: when the user asks for a weekday-specific attendance roster such as "이번주 수요일 출석해야 할 학생 명단 이미지로 줘", resolve the relative weekday into an explicit `YYYY-MM-DD` for the target date first, then query the class roster range for that single day.

## Routing rule

- Use `academy_class_roster_range` with `start_date == end_date == resolved date`.
- Keep `with_roster=true` when the user wants the actual student list/image.
- Do **not** use `academy_attendance_day` for pre-check-in roster questions.
- Do **not** treat `academy_schedule_range` as a substitute; it is for academy events, not class rosters.

## Practical date resolution

- Infer relative weekdays from the live system date.
- If the user says "이번주 수요일", compute the Wednesday in the current week on the agent side and pass that ISO date directly.
- If the request is already a specific date, use it as-is.

## Output expectation

- For Discord/image requests, render or return a single roster artifact only.
- Keep the response concise: date + roster basis + image attachment or summary.
