---
name: kbo-official-review-card
description: Use when the user asks for a KBO or Hanwha postgame review image. Fetch official GameCenter data, verify player photos, render a light HTML card, and deliver the verified MEDIA path.
version: 1.0.0
author: Miho Agent
license: MIT
metadata:
  miho:
    tags: [kbo, hanwha, review, image-card, gamecenter, html, discord, fastpath]
    related_skills: [kbo-report-cards, kbo-game-analysis, sports-report-card]
---

# KBO Official Review Card Fastpath

This skill captures the exact workflow used to build a fast, Discord-ready KBO postgame review image from official data.

Use it when the user says things like:

- `어제 경기 리뷰 이미지로`
- `한화 경기 리뷰 카드 만들어줘`
- `라이트 버전으로 리뷰 이미지`
- `어제 경기 먼저 리뷰`

The goal is simple: **fetch official facts, compose a clean light HTML card, verify every image, render/screenshot it, and send the exact MEDIA path**.

## Overview

For KBO review cards, speed comes from a narrow path:

1. Identify the finished game from thread context and confirm the exact `gameId` from the schedule/game-list page.
2. Pull the score summary first from `ws/Schedule.asmx/GetScoreBoardScroll`.
3. Use `ws/Main.asmx/GetKboGameList` to confirm starters, team context, and the actual finished game entry.
4. Pull box-score details only if needed; do **not** block the card on `GetBoxScoreScroll` if that endpoint returns a format error.
5. Pull verified player IDs and photos from the official KBO player search/profile pages when suitable; use a verified editorial action shot when the story reads better and the photo is clearly better than a headshot.
6. Build a **light / white / dense** HTML card with one clear hero image and a compact facts-first story.
7. Verify images and layout in-browser, then trim any excess vertical whitespace before shipping.
8. Save the final PNG in Miho media cache and send the exact MEDIA path.

Do **not** answer with a text-only recap when the user asked for an image.

## When to Use

Use this skill when:

- The user wants a postgame review card, not a preview.
- The game is already finished or clearly implied by thread context.
- You need the fastest repeatable way to create a Hanwha review image.
- The user asks for a lighter card style.
- You need to reuse the same workflow after a slow manual build.

Do not use this skill for:

- Standings-only requests.
- Pure text analysis.
- Unfinished game previews.
- Random KBO trivia.

## Fast Workflow

### Support files

- `references/editorial-rebuild-notes.md` — session notes for the article-style/action-shot rebuild pattern and final PNG verification.
- `references/review-2026-05-30-notes.md` — 2026-05-30 Hanwha/SSG review-session notes: score-summary endpoint shape, starter IDs, hero-photo selection, and compact layout result.

### 1) Ground the game

Use the most recent finished game implied by the conversation.
If the user says `어제 경기 리뷰 이미지` in a Hanwha context, assume they mean the last completed Hanwha game unless the thread says otherwise.

Preferred data source order:

1. KBO official GameCenter endpoints.
2. KBO official player search/profile pages.
3. Naver Sports only if the official path is missing something useful.

### 2) Pull official GameCenter review data

The fastest review path is the KBO official endpoint pair discovered from the review page source:

- `https://www.koreabaseball.com/ws/Schedule.asmx/GetScoreBoardScroll`
- `https://www.koreabaseball.com/ws/Schedule.asmx/GetBoxScoreScroll`

Typical POST payload:

```python
{
    'leId': 1,
    'srId': '0',
    'seasonId': '2026',
    'gameId': '20260529SKHH0'
}
```

Use the exact `gameId` for the finished game.
The response includes:

- score by inning
- R/H/E/B
- game time, stadium, crowd
- hitter tables
- pitcher tables
- decisive hit / home runs / errors / stolen bases / umpire notes

### 3) Pull player IDs and photos

Use the official player search endpoint:

- `https://www.koreabaseball.com/ws/Controls.asmx/GetSearchPlayer`

Example payload:

```python
{'name': '허인서'}
```

This returns `P_ID`, `P_NM`, `T_ID`, `P_LINK`, etc.

Official player photo pattern used by KBO player pages:

```text
https://6ptotvmi5753.edge.naverncp.com/KBO_IMAGE/person/middle/2026/{P_ID}.jpg
```

For this skill, **photo style matters**:

- Insert **only the day’s main protagonist** photo when possible.
- If a reliable sports-news action photo exists and reads better at card size, prefer it over a static headshot.
- Let the layout decide the orientation: if the copy is long, place the photo in a vertical slot; if the story is compact, keep it wide and cinematic. Do **not** force a fixed size just because a photo exists.
- Crop the image to feel like an article excerpt: clean rectangle, readable subject, no awkward empty margins.
- Use headshots only as fallback when no editorial/action photo is available.

Verify the image actually returns `200` and has non-zero bytes before embedding it.
If it fails, fall back to a team-color placeholder only as a last resort.

### 4) Build a light HTML card

Use a white/light background by default.
The user prefers dense, full-frame composition rather than empty space.

Recommended structure:

- top title + result pill
- short summary sentence
- R/H/E/B record block
- inning table
- turning-point bullets
- 3–4 player cards with verified photos
- pitcher usage / bullpen block
- `수확` and `숙제` split for Hanwha
- source line at the bottom

Design rules:

- The user prefers a light, dense card with consistent spacing.
- Do **not** add editorial/meta commentary in the visual copy. Use only game facts, concise recap language, and section labels.
- If the story is centered on one player, make that player the visual protagonist; keep extra players secondary or omit them.
- Let the amount of text decide the photo orientation and space allocation. Do not force a fixed photo size when the copy needs a different layout.

### 5) Verify images before screenshot

Always check image load status inside the page:

```js
Array.from(document.images).map(img => ({
  alt: img.alt,
  ok: img.complete && img.naturalWidth > 0,
  w: img.naturalWidth,
  h: img.naturalHeight
}))
```

Every important image should be `ok: true`.
If any photo fails, fix it before shipping.

### 6) Render and inspect

Preferred flow:

1. Write the HTML to `~/.miho/assets/kbo-cards/<date>/`.
2. Open the file in the browser.
3. Screenshot the rendered page.
4. Inspect the screenshot visually.
5. Save the final PNG to `~/.miho/media_cache/`.
6. Deliver the exact `MEDIA:` path.

If you already verified a correct PNG and the user simply says it did not arrive, resend the verified path instead of rebuilding.

## Practical Endpoint Notes

### Scoreboard

`GetScoreBoardScroll` is useful for:

- final score
- stadium
- crowd
- first/last time
- inning score table
- summary win/loss lines

### Box score

`GetBoxScoreScroll` is useful for:

- decisive hit
- HR / 3B / 2B / stolen base / error / 포일 / 폭투
- hitter tables
- pitcher tables
- R/H/E/B totals

### Player lookup

Use `GetSearchPlayer` when you need:

- player IDs for photos
- team affiliation
- position labels
- exact official spelling

## Common Pitfalls

1. **Answering with text only.**
   The user asked for an image. Always finish with a verified image attachment.

2. **Using the schedule page instead of the box-score path.**
   For finished games, the official GameCenter endpoints are faster and more reliable.

3. **Forgetting to verify photo URLs.**
   A broken player photo ruins the card. Check `status 200` and non-zero bytes before embedding.

4. **Forcing a box-score dependency when the summary is enough.**
   If `GetBoxScoreScroll` throws a format error, use the score summary plus article copy and keep moving. The review card should still ship.

5. **Making the hero image too small or too headshot-like.**
   For this user, the strongest review cards usually use one clear action shot with a clean crop.

6. **Producing a tall, empty card.**
   The preferred result is compact and full-frame, with excess vertical whitespace trimmed before export.

7. **Mixing up yesterday/today.**
   Health-style date discipline applies here too: the review should reflect the actual finished game, not a nearby fixture.

## Verification Checklist

- [ ] Finished game identified correctly from thread context
- [ ] Official score and box-score data fetched
- [ ] Player IDs and photos verified
- [ ] HTML card uses a light / white base
- [ ] Inning table, R/H/E/B, and key bullets are present
- [ ] `document.images` shows all important images as loaded
- [ ] Rendered PNG inspected visually
- [ ] Footer/source line included
- [ ] Final response includes the exact verified `MEDIA:` path

## One-Shot Recipe

When the user asks for a Hanwha review image:

1. Pull the official KBO game-center review data for the most recent finished Hanwha game.
2. Extract score, inning table, R/H/E/B, decisive hit, HR, and pitcher lines.
3. Decide the **single main protagonist** for the card first; only add extra players if the story truly needs them.
4. Look up the needed player(s) with `GetSearchPlayer` and verify the photo source.
5. Fetch player photos from the official KBO photo path or a reliable editorial/action photo source and embed them as data URIs.
6. Build a light HTML card and let the content decide whether the photo block is vertical or horizontal.
7. Open in browser, verify image load and layout.
8. Save PNG under `~/.miho/media_cache/`.
9. Send the `MEDIA:` path back to Discord.

If the user says `라이트 버전`, keep the background light, increase spacing slightly, and avoid heavy dark hero blocks.

If the user says `이미지로`, do not drift into a text summary. Ship the card.
