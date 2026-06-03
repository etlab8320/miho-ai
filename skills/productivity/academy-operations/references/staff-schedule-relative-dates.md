# Staff schedule relative-date lookup

Use this pattern when the user asks a relative question like:

- "내일 누가 근무해"
- "오늘 근무자"
- "어제 누가 출근했어"

## Verified behavior

The public staff schedule tool wrapper requires an explicit `YYYY-MM-DD` date. When the user gives a relative date, resolve it first, then call the underlying schedule lookup with the resolved day.

## Practical flow

1. Resolve the date from the system clock in the current locale.
2. Query `staff_schedule_for_day(client, target_day)` or the matching API endpoint.
3. Format only the scheduled instructors grouped by slot.
4. If the user asked "누가 근무해", report future/scheduled staff, not actual attendance.

## Notes

- For attendance questions, use the staff attendance endpoint instead.
- Do not ask the user to retype a date when the relative date is already explicit in the message.
- Keep the answer short: date + slot + names.
