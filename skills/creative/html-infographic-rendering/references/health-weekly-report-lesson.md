# Weekly Health Report Lesson (2026-05-31)

This note captures the layout and verification pattern that worked for the user's health summaries.

## What the user wanted
- Daily health card on normal days.
- On Sundays, a **separate weekly report image** in addition to the daily card.
- The weekly report should feel like a **report**, not a loose set of cards.
- Include charts for values that have a time series:
  - weight trend
  - calorie / intake flow
  - blood pressure only on days it was actually measured

## Working layout
- Bright, clean background.
- Top headline + date range.
- Summary metric chips near the top.
- Left: food / daily timeline.
- Right: blood pressure / judgment panel.
- Bottom: a short one-line conclusion.

## Useful design choices
- Use large readable numbers for key metrics.
- Keep text short and high-signal.
- Prefer a report tone over a decorative card tone.
- Make the report visually dense enough that it feels full, but do not overcrowd the charts.

## Verification pattern that prevented wasted renders
- Render HTML to PNG.
- Check the actual document height before deciding screenshot size.
- If the screenshot leaves a large empty bottom band, reduce the canvas min-height or the capture height; do not accept the blank space as intentional.
- Verify the PNG visually after every major resize.

## Pitfall
- If the report has both daily and weekly versions, keep them as **two separate artifacts** rather than trying to force both into one design.
- The weekly report should stay a report-style overview; the daily card should remain a concise single-day snapshot.
