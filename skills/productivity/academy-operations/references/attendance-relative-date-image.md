# Relative-date roster image routing

Use this when the user asks for a roster image with a relative day phrase such as:

- `이번주 수요일 출석해야 할 학생 명단 이미지로 줘`
- `다음주 월요일 출석할 학생 명단`
- `오늘 출석할 학생 명단 이미지로 줘`

## Routing rule

1. Resolve the relative date into an explicit `YYYY-MM-DD` using the live system date.
2. Call `academy_class_roster_range` with:
   - `start_date == end_date == resolved_date`
   - `with_roster=true`
   - `image=true` when the user asked for an image
3. Do **not** use `academy_attendance_day` for class-roster questions.
4. For future dates, treat zero attendance as expected and keep the class roster result; the roster is the source of "who should attend," not the check-in endpoint.
5. If a local wrapper cannot infer the Discord user binding, fall back to the stored academy token for read-only lookup instead of claiming the roster is unavailable.

## Why

- `attendance_day` reflects check-in status and can show zeroes before check-in happens.
- `class_roster_range` is the correct source for "who should attend this class date".
- Image requests should go straight through the roster renderer so the final answer is one MEDIA attachment, not a text summary plus a separate image.

## Output

Return the MEDIA image path plus a short Korean summary that mentions:

- the resolved date
- total classes / students
- only actionable exceptions

Keep the reply concise.
