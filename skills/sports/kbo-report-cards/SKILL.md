---
name: kbo-report-cards
description: Create Discord-ready Korean KBO prediction, recap, standings, and weekly review image cards with HTML-first rendering, verified player photos, and strict visual QA.
version: 1.0.0
platforms: [linux, macos, windows]
metadata:
  miho:
    tags: [kbo, baseball, hanwha, prediction, recap, standings, html, image-card, korean]
    related_skills: [kbo-game-analysis, sports-report-card]
---

# KBO Report Cards

Use this skill when the user asks for KBO or Hanwha analysis as an image:

- `오늘 한화 경기 리뷰 이미지로`
- `오늘 KBO 승부예측 이미지`
- `키플레이어 사진 넣어서`
- `순위표도 같이`
- `지난주 한화 리뷰`

This skill owns the visual card. Pair it with `kbo-game-analysis` for current facts and baseball judgment.

## Core Rule

For normal KBO image requests, **do not answer with a plain text summary only**.

Build source HTML first, render a PNG, verify it visually, then send:

```text
MEDIA:/absolute/path/to/verified-card.png
```

## Data Grounding

Verify current data before designing. Prefer:

- KBO official schedule, GameCenter, box score, standings, and player pages.
- Naver Sports KBO schedule/record/relay endpoints when they provide richer box-score, relay, or photo data.
- Team official announcements and reliable Korean sports news for lineup, injuries, and action photos.

Useful endpoint notes are in `references/naver-kbo-data-sources.md`.

Do not invent scores, player photos, starters, lineups, WPA, records, or article images.

## Image Types

### Prediction Card

Use for pre-game picks and `승부예측`.

Required content:

- Matchup, date, time, venue.
- Probable starters when verified.
- Expected score, winner, and confidence range.
- Team standings context: rank, W-L-D, win pct, games back, recent 10, streak, home/away.
- Team basic stats when available: AVG, runs, HR, ERA, WHIP.
- Previous-game result and useful context when available.
- 2-line Korean rationale.
- Key players from recent form and matchup context, not season AVG alone.

### Postgame Review Card

Use for `경기 리뷰`, `경기끝`, `오늘 한화경기 리뷰`.

Required content:

- Final score, venue, date, and result.
- Inning score table plus R/H/E/B.
- Turning points: 3-4 concrete bullets.
- Starter line and bullpen usage.
- 3-5 key players with photos and compact stat lines.
- For Hanwha, separate `수확` and `숙제`; do not hide bullpen, defense, walk, or stranded-runner issues after a win.

### Standings Card

Use a separate image when the user asks for `순위표`.

- Show all 10 teams.
- Highlight Hanwha when relevant.
- Use `원정`, never `방문`.
- Include recent 10, streak, home/away, and games back.
- Add one short interpretation block if space allows.

### Weekly Review Card

Use for `지난주`, weekly cron-style review, or no-game weekly summary.

- Query actual official games for the requested period.
- Show W-L, runs scored, runs allowed, run differential.
- Include game-by-game mini table.
- Include best game, most frustrating game, weekly key players, `수확`, `숙제`, and next watch points.

## Player Photos

Photo effort is mandatory for image cards.

Preferred order:

1. Official KBO/Naver player photo when player ID is available.
2. Team official player page or announcement photo.
3. Reliable Korean sports news action photo for the exact game/player.
4. Team-color silhouette or initials fallback only after lookup fails.

Rules:

- For reviews, action/news photos are better than static headshots when clearly sourced.
- Do not use broken remote image URLs.
- When possible, embed player photos as data URIs before screenshot so Discord receives a complete image.
- Verify every image with `document.images`: `complete`, `naturalWidth`, and `naturalHeight`.
- Put photo and text in separate grid areas. Never overlay stats on faces.

## HTML-First Rendering

Default output:

- Prediction: 1080x1350 portrait or 1600x900 wide if requested.
- Review: 1400x1600 to 1600x1900, or full-page screenshot when content is tall.
- Save HTML under Miho state, e.g. `~/.miho/assets/kbo-cards/<date>/`.
- Save PNG under Miho media cache, e.g. `~/.miho/media_cache/`.

Use Korean-safe font stack:

```css
font-family: "Goyang", "Pretendard", "Noto Sans KR", "Apple SD Gothic Neo", sans-serif;
font-variant-numeric: tabular-nums;
```

For card construction:

- Use CSS grid/flex with explicit gaps.
- Use white/light background by default.
- Use strong team-color accents, not full dark backgrounds.
- Keep scores, team names, and stat labels in separate containers.
- Use fixed photo containers with `object-fit: cover`.
- Avoid manual Pillow coordinate drawing for dense cards.

Quality rules are in `references/kbo-card-quality.md`.

## Final QA

Before sending:

- HTML file exists and opens.
- PNG came from HTML screenshot/rendering.
- Korean text is rendered and not clipped.
- Bottom/footer is not cropped.
- Player photos are visible or fallback is intentional.
- Score, teams, and result are readable at Discord/mobile size.
- No overlapping inning table, stat cards, photos, or source line.
- Final answer uses the exact verified media path.

If the user says the image did not arrive, resend the verified `MEDIA:` path immediately after checking that the file path passes Miho media delivery validation.
