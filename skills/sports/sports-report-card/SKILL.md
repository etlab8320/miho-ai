---
name: sports-report-card
description: Create polished Korean sports preview/review images as HTML-first report cards, then render and send them as native media.
version: 1.0.0
platforms: [linux, macos, windows]
metadata:
  miho:
    tags: [sports, report-card, html-render, infographic, korean, discord-media]
    related_skills: [kbo-game-analysis, baoyu-infographic, claude-design]
---

# Sports Report Card

Use this skill when the user asks for a sports preview, review, recap, or prediction as an image.

This is the visual layer. Pair it with a domain analysis skill such as `kbo-game-analysis` for facts and judgment.

## Output rule

Create the report as HTML/CSS first, render it to a PNG, inspect it, then send it with `MEDIA:<path>`.

Do not make a plain matplotlib chart, spreadsheet-looking figure, or low-density text screenshot unless the user explicitly asks for that.

## Required workflow

1. Verify current game facts with official or reliable sources.
2. Gather visual assets:
   - Use key player or stadium photos when a reliable, usable source is available.
   - Prefer team/player official pages or reputable news images.
   - If image rights or source quality is unclear, use team colors, jersey-number typography, silhouettes, or clean stat modules instead of fabricating photos.
3. Build a single HTML canvas:
   - Default size: `1080x1350` portrait for Discord/mobile.
   - Alternative: `1600x900` landscape when the user asks for wide image.
   - Use CSS grid, strong hierarchy, and stable fixed dimensions.
4. Typography:
   - Korean default: Goyang, Pretendard, Noto Sans KR, Apple SD Gothic Neo, sans-serif.
   - Use tabular numerals for scores, innings, ERA, AVG, and win probabilities.
   - Do not let Korean text overflow boxes.
5. Visual structure:
   - Top: league/date/matchup and final score or start time.
   - Hero: winning/featured team signal with 1-2 key player photo slots.
   - Middle: 3-5 key moments or matchup keys.
   - Bottom: stat strip, next game note, and small source/date line.
6. Render to PNG under Miho media cache, usually `~/.miho/media_cache/`.
7. Inspect the PNG with vision or screenshot review:
   - Korean text rendered correctly.
   - No clipped text.
   - Player photos are not stretched.
   - Score and teams are immediately readable.
   - No overlap between inning lines, footnotes, or bottom labels.
8. Send the image as native media:

```text
MEDIA:/absolute/path/to/report.png
```

## Style direction

For Korean baseball, use a sharp sports-broadcast card, not a generic infographic.

- Strong team color accents, but keep the base clean.
- Use real baseball texture sparingly: field lines, scorebug, dugout/photo panels.
- Prefer editorial density over cute decoration.
- Cards should feel like a professional sports media graphic.

## Guardrails

- Never invent player photos, records, scores, lineups, injuries, or quotes.
- If the user asks for a prediction, show confidence as a range, not a guarantee.
- If a key player photo cannot be sourced safely, say so briefly and use a non-photo design fallback.
- Image quality matters more than speed when the user explicitly asks for an image.
