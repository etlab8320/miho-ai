# Weekly Health Report Layout Notes

Session lesson: the user prefers a **report-shaped weekly health image** rather than a card-shaped collage.

## What the user wanted
- A Sunday evening image that summarizes the past week.
- A more report-like composition: headline, KPI strip, graphs, daily summary rows, and a closing verdict.
- Weekly trends for numeric fields:
  - weight as a line chart
  - calories as a bar chart
  - blood pressure only on days it was measured
- A preview first, then iterative corrections before cron registration.

## What worked
- A bright paper-like background with soft borders and rounded modules.
- A top header with the report date and short explanatory subtitle.
- A KPI strip with 4–5 high-signal metrics.
- A large weight trend chart as the main anchor.
- A timeline-style daily log summary on the right.
- A smaller blood-pressure panel/gauge next to a calorie mini-chart.
- A closing summary block with the weekly verdict.

## Important tuning lessons
- The layout should feel like a **single report page**, not a stack of unrelated cards.
- The user will inspect the image visually before approving cron automation, so a good preview matters.
- Do not leave a visible gray footer or blank band at the bottom of the rendered PNG.
- If the screenshot is too short, increase the Chrome viewport height and re-render; do not assume the first render is good enough.
- When the preview still feels sparse, add density by widening the report structure rather than shrinking cards.
- Keep day summaries short so the charts remain the focus.

## Reusable structure
1. Title + subtitle
2. Summary chips / KPI strip
3. Weight trend chart
4. Calorie chart
5. Blood-pressure panel
6. Daily log summary
7. Weekly verdict / next-week focus

## Verification checklist
- No clipping at the bottom.
- No overlapping text.
- Korean text stays readable at full screenshot scale.
- Charts are visually distinct and legible.
- The whole page reads as a report, not a collage.
