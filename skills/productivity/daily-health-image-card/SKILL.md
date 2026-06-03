---
name: daily-health-image-card
description: Turn a day’s health, meal, weight, exercise, and condition notes into a polished Discord-ready image card, using the user’s preferred clean bright layout.
version: 1.0.0
platforms: [macos, linux]
metadata:
  miho:
    tags: [health, image-card, discord, korean, daily-log, infographic]
---

# Daily Health Image Card

Use this skill when the user wants the day’s health log turned into an image card in the style they approved: clean, bright, readable, and concise Korean.

## When to use

- The user asks for “오늘꺼 이미지로”, “카드스타일”, “이미지로 정리”, or a daily health summary image.
- The message includes weight, meals, exercise, sleep, supplements, or condition notes.
- The user wants the result ready for Discord.
- If the user says **리포트**, **주간 리포트**, or asks for a Sunday recap, switch to the weekly-report variant in addition to the daily-card logic.
- If the user asks for a **Monday weekly routine / week plan image**, use the weekly routine variant: one report page, recent weight at the top, blood pressure / blood sugar check rhythm, and 월~토 meal/exercise structure. See `references/weekly-routine-brief.md`.

## Weekly report variant

Use the same health data, but render it as a **single polished report page** instead of a compact day card.

- Show corrected weights and corrected meal history immediately when the user supplies fixes.
- Include summary chips, trend charts, blood pressure only on measured days, and a short judgment / next-step block.
- Make sure the page still reads as one composed report, not a stack of unrelated panels.
- Keep a calm report tone. Do NOT put meta words like “정정 반영” / “수정 반영” / status notes into the visible title or headers — the title is just the report name (e.g. “주간 건강 리포트”).
- For weekly plans, vary the menu and workout pattern from week to week; do not reuse the same meals/exercises mechanically. Keep the structure stable, but change the actual food and workout examples each week so the image does not feel monotonous.
- See `references/weekly-health-report-notes.md` for session-specific guidance and render notes.

## Design rules from the user

- Use a **bright paper-like background**, not a dark dashboard.
- Make the layout feel like a **real image card**, not a plain text dump.
- Keep Korean text **large and readable**.
- Show only the day’s relevant health notes; do **not** mix in stale days.
- Include:
  - date
  - body weight if present
  - meal summary
  - exercise if present
  - short judgment
  - one next-step line
  - **total calories when the day includes food logs**
  - if calories are estimated, label them clearly as **대략 / 전후 / 추정**
- Keep the tone **neutral, concise, and human**.
- Prefer phrases like “조금 아쉬움”, “모자란 편”, “흐름은 괜찮음”, not harsh or shaming language.
- The card should be compact enough for Discord but not cramped.

## Workflow

1. **Collect the day’s health entries**
   - Read the thread’s RAG/messages.
   - Keep only current-date health messages.
   - Focus on weight, meals, exercise, sleep, supplements, and condition.

2. **Summarize the day**
   - Weight: single line with context if timing matters.
   - Meals: list or grouped summary.
   - Exercise: add if present.
   - Judgment: one sentence, plain Korean.
   - Next step: one practical line.

3. **Render as HTML infographic**
   - Use the `html-infographic-rendering` skill.
   - Prefer a wide canvas with a bright background.
   - Use large typography and clear spacing.
   - Avoid too many tiny sections.
   - Ensure the card fills the frame without feeling sparse.

4. **Export to PNG**
   - Save under:
     - `~/.miho/media_cache/health-nightly/<date>-health-card.html`
     - `~/.miho/media_cache/health-nightly/<date>-health-card.png`
   - After saving, print the PNG's absolute path as a structured line so the gateway can attach it even if you forget the MEDIA: line later. Run e.g.:
     `echo "{\"path\":\"$HOME/.miho/media_cache/health-nightly/<date>-health-card.png\",\"status\":\"created\"}"`
   - Re-render if the lower part is clipped, the layout feels too sparse, or the card no longer fills the frame well.
   - If the user asked for a scheduled image to be updated with one extra field (for example, total calories), patch the existing cron/image workflow instead of generating a separate standalone redesign unless they explicitly ask for a new concept.

5. **Verify visually**
   - Check that the Korean text is readable.
   - Check that the bottom is not cut off.
   - Check that the total calories chip/line is visible when present.
   - Check that the overall composition feels like a real card.

6. **Deliver**
   - End your reply with the attachment line `MEDIA:/absolute/path/to/file.png` on its own line — this is the ONLY thing that actually ships the image. No MEDIA: line = the user gets text with no picture.
   - If you say you are sending an image, the `MEDIA:` line MUST be in the SAME reply. Never write “이미지:” / “보낼게” without the `MEDIA:` line in that same message.
   - If the user asks for “from the day I started recording” or similar, deliver the existing dates in chronological order, not just the latest card.
   - Keep the reply short and direct.

## Copy structure

A good card usually follows this structure:

- Header: date + short verdict
- Left or top block: weight / condition
- Middle block: meals
- Small block: exercise / supplements if relevant
- Bottom block: judgment + next step

## Pitfalls

- Don’t reuse yesterday’s content by accident.
- Don’t make the text too small just to fit more detail.
- Don’t leave the canvas visually empty.
- Don’t overstate weight changes from a single measurement.
- If the user measured at a different time than usual, mention that the number may be slightly shifted by timing.
- Don’t omit total calories on days where food intake is the main subject.
- If the user asks to add or change a field in the scheduled nightly/cron health card, patch the existing cron prompt/layout and rerun that job; do not create a separate standalone redesign unless they explicitly ask for a new concept.
- Don’t split the series awkwardly; if the user wants all logged days, provide the whole sequence in date order.
- For weekly reports, don’t just paste the latest day’s narrative — rebuild the trend from the corrected underlying numbers.

## Preferred phrasing

- “오늘은 흐름을 잘 잡은 날”
- “보강해서 버틴 날”
- “조금 흔들렸지만 전체 흐름은 괜찮음”
- “내일은 같은 조건으로 다시 확인”

## Notes

This skill is meant to preserve the exact layout direction the user liked, so future daily cards can be generated consistently without re-asking about style.
