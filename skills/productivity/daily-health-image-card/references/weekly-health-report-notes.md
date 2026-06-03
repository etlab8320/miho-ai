# Weekly Health Report Notes

Session-specific guidance for the weekly health report variant that sits alongside the daily health card.

## What changed in this session

- The user preferred a **weekly report** for the Sunday recap, not another daily card.
- The weekly output should feel like a **single polished report page**, with a strong headline, summary chips, weight trend, calorie trend, blood pressure trend, and a short judgment block.
- When the user corrects past entries, **rebuild the weekly data from the corrected values immediately** rather than trying to patch the old narrative by hand.

## Practical rendering notes

- The weekly report can be taller than the daily card, but it still needs to feel like one composed page rather than stacked loose panels.
- If the bottom edge looks clipped or the page ends with an obvious empty grey band, increase canvas height and re-render.
- A final image around **1800px wide** with enough vertical room for the full report has worked well in this session.

## Data correction example from this session

- 2026-05-25 weight: **107.5kg**
- 2026-05-26 weight: **106.78kg** (card display rounded to **106.7kg**)
- 2026-05-27 weight: **105.7kg**
- The weekly trend and average should reflect these corrected values.

## Tone

- Use neutral Korean.
- Use a neutral report tone (“흐름”, “리포트”, “주간 요약”). Never surface meta words like “정정 반영” / “수정 반영” in the visible title or headers — those are internal notes, not part of the report text.
- The user likes the output to read as a report, not a chat transcript.
