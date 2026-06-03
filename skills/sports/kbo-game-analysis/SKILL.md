---
name: kbo-game-analysis
description: Preview, review, and probabilistically analyze KBO games using current lineups, starters, standings, recent form, and context.
version: 1.0.0
platforms: [linux, macos, windows]
metadata:
  miho:
    tags: [kbo, baseball, sports, preview, review, prediction]
    related_skills: [kbo-report-cards, sports-report-card, web]
---

# KBO Game Analysis

Use this skill when the user asks for KBO game previews, reviews, team/player form, matchup analysis, or win-probability style predictions.

If the user asks for an image, card, graphic, Discord-ready report, `이미지로`, `리뷰 이미지`, `승부예측 이미지`, or key-player photos, pair this skill with `kbo-report-cards`. This skill decides the baseball content; `kbo-report-cards` owns the HTML-first visual card and MEDIA delivery.

## Grounding rule

KBO information is time-sensitive. Always verify current data before previewing or predicting a game.

For win-probability style predictions, do not guess from rankings alone. Always inspect:

- the KBO 기록실 / official team records for the likely starter and key lineup candidates
- each side’s recent five-game flow, not just season totals
- starter matchup, bullpen workload, and lineup/injury/rest context
- park and weather effects when relevant

Prefer current sources:

- KBO official schedule, standings, box scores, and player records: `kbo.co.kr`
- Naver Sports schedule plus `/preview` endpoint for pregame context: probable starters, recent five-game flow, standings snapshot, season head-to-head, top-player recent stats, and lineup candidates.
- Team official announcements for starters, injuries, roster moves
- Reliable Korean sports news for lineup and weather context
- Weather source for stadium-specific game conditions

## Preview checklist

- Date, venue, start time
- Probable starters and bullpen availability
- Recent 5-game flow, then extend to 10 games only if it changes the read
- Head-to-head context, but do not over-weight it
- Lineup/injury/rest news
- Key lineup candidates’ record signals from the KBO 기록실, especially the players most likely to start
- Park/weather effects
- Tactical keys for both teams
- Prediction with confidence band, not a guarantee

## Review checklist

- Final score and inning flow
- Starting pitcher performance
- Bullpen leverage moments
- Key plate appearances and defensive mistakes
- Managerial decisions
- What changed for the next game

## Image/card routing

For KBO image requests:

- Produce HTML first, then render a PNG.
- Use `kbo-report-cards` for the visual structure, photo rules, and QA checklist.
- Include player photos when reliable official/team/news sources are available.
- Verify the rendered image before sending.
- Final response should include the verified `MEDIA:/absolute/path.png`.

Do not make a low-density Pillow/matplotlib-style image for KBO report cards unless HTML rendering is unavailable and the user accepts a fallback.

## Prediction workflow

When the user asks for 승부예측:

1. Identify the likely starters and the probable lineup candidates.
2. Check the KBO 기록실 / official player records for those likely lineup players, not just the team names.
3. Read the last five games for each team to understand current flow.
4. Compare starter matchup, bullpen load, platoon edges, and park/weather.
5. Give a provisional pick with a short reason and a confidence band.
6. If lineups/starters are still uncertain, say exactly what is not confirmed.

Session-specific prediction preferences from the 2026-05-30 rebuild are condensed in `references/session-2026-05-30-layout-and-prediction-notes.md`.

## Prediction guardrails

- This is analysis, not betting advice.
- State uncertainty and assumptions.
- Do not guarantee outcomes.
- If lineup/starters are unconfirmed, say the prediction is provisional.
