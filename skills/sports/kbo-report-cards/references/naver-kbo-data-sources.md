# Naver/KBO Data Sources for KBO Cards

Use official KBO data first when available. Naver Sports can be a practical companion source for schedule discovery, final records, relay summaries, and richer mobile GameCenter data.

## Daily Schedule

```text
https://api-gw.sports.naver.com/schedule/games?fields=basic,schedule,baseball&upperCategoryId=kbaseball&categoryId=kbo&fromDate=YYYY-MM-DD&toDate=YYYY-MM-DD&size=100
```

Useful fields from `result.games[]`:

- `gameId`
- `gameDate`, `gameDateTime`, `stadium`
- `homeTeamCode`, `homeTeamName`, `homeTeamScore`
- `awayTeamCode`, `awayTeamName`, `awayTeamScore`
- `winner`, `statusCode`, `statusInfo`
- `homeStarterName`, `awayStarterName`
- `winPitcherName`, `losePitcherName`

Hanwha team code is usually `HH`.

## Game Record / Box Score

```text
https://api-gw.sports.naver.com/schedule/games/{gameId}/record
```

Useful paths under `result.recordData`:

- `scoreBoard.inn.away/home` — inning-by-inning runs.
- `scoreBoard.rheb.away/home` — R/H/E plus walk/HBP summary.
- `etcRecords[]` — decisive hit, HR, extra-base hits, errors, umpires, notes.
- `pitchingResult[]` — W/L/H/S pitcher summary.
- `pitchersBoxscore.home/away[]` — IP, H, R, ER, K, BB, HR, W/L/S/H, ERA.
- `battersBoxscore.home/away[]` — AB, H, HR, RBI, R, inning result cells.
- `todayKeyStats.home/away` — hits, HR, errors, strikeouts, and similar.
- `homeTeamNextGames[]`, `awayTeamNextGames[]` — next game/series context.
- `homeStandings`, `awayStandings` — rank, W/L/D, win rate, team ERA/AVG/HR.

## Relay / Inning Data

```text
https://api-gw.sports.naver.com/schedule/games/{gameId}/relay
```

Useful paths:

- `textRelayData.inningScore.home/away`
- `textRelayData.homeLineup`, `textRelayData.awayLineup`
- `textRelayData.textRelays[]`

## Request Notes

Use browser-like headers:

```text
User-Agent: Mozilla/5.0
Referer: https://m.sports.naver.com/
```

If sibling endpoints such as `/summary` or `/boxscore` return 403, `/record` and `/relay` are usually enough for review cards.

## Construction Pattern

- Header: date, stadium, league, source.
- Score block: final score and R/H/E/B.
- Inning flow: 1-9 grid.
- Turning points: 3-4 bullets from actual plays.
- Faces of the game: 3-5 players with stat lines and photos.
- Numbers block: hits, walks/HBP, HR, errors, strikeouts, next game.

Always visually verify the final card for Korean rendering, photo loading, clipping, and overlap.
