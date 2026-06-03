# KBO Review Endpoint Workflow

This reference captures the official-data path used for KBO postgame review cards.

## When to use

Use this workflow when the user asks for:

- `경기 리뷰 이미지`
- `어제 경기 리뷰`
- `한화 경기 끝나고 리뷰`
- `리뷰 카드`

Do not substitute a preview/schedule response just because the user mentioned KBO generally. Resolve to the most recent completed game that matches the conversation context.

## Official endpoints

### 1) Scoreboard / inning table

`POST /ws/Schedule.asmx/GetScoreBoardScroll`

Typical payload keys:

- `leId`
- `srId`
- `seasonId`
- `gameId`

Returned fields are used for:

- stadium name
- crowd
- start/end time
- inning score table
- team records
- final score

### 2) Box score / hitters / pitchers / deciding play

`POST /ws/Schedule.asmx/GetBoxScoreScroll`

Same payload shape as above.

Returned fields include:

- `tableEtc`
- `arrHitter`
- `arrPitcher`
- `realMaxInning`

Use this for:

- decisive hit
- home runs
- pitching lines
- hitter stat lines
- bullpen usage

### 3) Player lookup for IDs and team

`POST /ws/Controls.asmx/GetSearchPlayer`

Payload:

- `name=<player name>`

Returned fields useful for card generation:

- `P_ID`
- `P_NM`
- `T_ID`
- `T_NM`
- `POS_NO`
- `P_LINK`

## Photo pattern

Official player images are typically reachable at:

`https://6ptotvmi5753.edge.naverncp.com/KBO_IMAGE/person/middle/2026/{playerId}.jpg`

If that fails, the page may fall back to `no-Image.png`; do not ship a broken icon.

## Practical notes from the 2026-05-29 Hanwha vs SSG review

- Scoreboard endpoint returned `code=100` for the game id `20260529SKHH0`.
- Box score endpoint returned:
  - final score: Hanwha 4, SSG 3
  - deciding hit: 허인서 5회 무사 1루 좌월 2점 홈런
  - supporting homer: 강백호 6회 2점 홈런
  - bullpen line: 박상원 홀드, 이민우 세이브
- Player lookup confirmed the ID/photo path for key players:
  - 허인서 `52764`
  - 강백호 `68050`
  - 박상원 `67703`
  - 이민우 `65616`

## Verification checklist

- Parse the JSON before designing.
- Verify every image URL loads.
- Embed photos as data URIs before screenshot when possible.
- Render the HTML and inspect it before sending.
- Prefer the review card over text when the user asked for an image.
