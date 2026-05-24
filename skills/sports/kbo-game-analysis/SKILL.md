---
name: kbo-game-analysis
description: Preview, review, and probabilistically analyze KBO games using current lineups, starters, standings, recent form, and context.
version: 1.0.0
platforms: [linux, macos, windows]
metadata:
  miho:
    tags: [kbo, baseball, sports, preview, review, prediction]
    related_skills: [web]
---

# KBO Game Analysis

Use this skill when the user asks for KBO game previews, reviews, team/player form, matchup analysis, or win-probability style predictions.

## Grounding rule

KBO information is time-sensitive. Always verify current data before previewing or predicting a game.

Prefer current sources:

- KBO official schedule, standings, box scores, and player records: `kbo.co.kr`
- Team official announcements for starters, injuries, roster moves
- Reliable Korean sports news for lineup and weather context
- Weather source for stadium-specific game conditions

## Preview checklist

- Date, venue, start time
- Probable starters and bullpen availability
- Recent 5-10 game form
- Head-to-head context, but do not over-weight it
- Lineup/injury/rest news
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

## Prediction guardrails

- This is analysis, not betting advice.
- State uncertainty and assumptions.
- Do not guarantee outcomes.
- If lineup/starters are unconfirmed, say the prediction is provisional.
