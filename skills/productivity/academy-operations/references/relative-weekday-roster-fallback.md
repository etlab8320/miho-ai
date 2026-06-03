# Relative weekday roster fallback

Session lesson: `이번주 수요일 출석해야 할 학생 명단 이미지` should be handled by resolving the weekday into an explicit ISO date on the agent side and calling `academy_class_roster_range` with `start_date == end_date == resolved date` and `with_roster=true`.

## Verified pattern

1. Read the live system date.
2. Compute the target weekday locally.
3. Call `academy_class_roster_range` with explicit `start_date` / `end_date`.
4. If the wrapper says the date is missing, fix the arguments and retry — do not ask the user to restate the date.
5. If the API says the academy binding is expired, stop and tell the user to run `/academy login`.
6. For Discord image requests, return a single roster image only.

## Important nuance

A weekday roster request is **not** an attendance-status query. Use the class roster path, not the daily attendance path, because attendance counts can be zero before check-in while a real class roster still exists.
