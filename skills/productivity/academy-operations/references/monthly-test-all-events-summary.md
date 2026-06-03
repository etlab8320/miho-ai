# Monthly test all-events summary notes

Use this when 맥스 asks for a Peak 월말테스트 summary across **all events** for a specific school, especially after a correction like “전체 종목임마”.

## Key lesson

When the user says `전체 종목`, the output should cover every available event in the monthly test. Do **not** narrow the response to a single event or a single average.

## Output shape

For each event, show:

- event name
- 남학생 평균
- 남학생 범위
- 여학생 평균
- 여학생 범위
- 전체 평균
- 전체 범위

Use the event's own unit and direction, and compute values from the monthly-test participant payload.

## Presentation notes

- Keep male and female averages separate by default.
- Overall averages are useful as a third column, not a replacement for gender-separated reporting.
- Round averages to two decimals at most; avoid noisy floating precision in the final image or text.
- If a participant has no records for an event, exclude them from that event's average and note the missing record only if needed.
- For Discord images, **use the `academy_report_image` tool** (don't hand-draw in execute_code): `columns`=각 종목+단위, `groups`=남학생/여학생(각 `avg_label`), `rows`=학생별. 도구가 정렬·성별 평균·밝은 트렌디 디자인·스탬프를 보장한다.
