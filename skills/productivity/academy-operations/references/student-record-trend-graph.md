# Student record trend graph workflow

Use this when the user asks for a **single student's recent record trend as an image**, e.g. “김동혁 최근 5회차 실기기록 각 종목별 그래프로 이미지로 줘”.

## Workflow

1. **Resolve the student name first.**
   - If the exact name fails, try short PACA substrings before asking again.
   - Present the closest live match with a caveat when the user typo is obvious.

2. **Fetch the student's Peak records.**
   - Resolve the PACA student to the linked Peak student.
   - Pull `list_peak_records(peak_student_id)`.
   - Keep all event names exact; do not mix similar tests.

3. **Build the chart window.**
   - For each event, use the **latest 5 distinct measurement dates** for that student.
   - One record per event per date is enough; if multiple rows exist on the same date, use the latest `created_at`.
   - Leave gaps blank when an event has no record on one of those dates.

4. **Direction matters.**
   - `direction = higher` → rising line is good.
   - `direction = lower` → lower numbers are better; color or label the series so that the user can tell it is a time-based improvement even when the line goes down.

5. **Render legibly.**
   - Put the student identity and date range in a header card.
   - Use one panel per event.
   - Add a small latest-value label and a small change-vs-previous label.
   - Run a visual QA pass to catch clipped titles, legends, or date ticks before delivering the image.

## Practical notes

- If a target event has no record in the latest 5 dates, show `최근 5회차 내 기록 없음` instead of inventing a point.
- Keep the chart palette consistent across panels so the image reads as one card set.
- Keep the text short; the graph should carry most of the meaning.
