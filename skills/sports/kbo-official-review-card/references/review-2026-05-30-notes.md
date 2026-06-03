# 2026-05-30 Hanwha vs SSG review notes

Session-specific notes for the 2026-05-30 Hanwha review card workflow.

## Verified game context
- Game: `20260530SKHH0`
- Final score: Hanwha 13, SSG 10
- Venue: Daejeon
- Crowd: 17,000
- Result: Hanwha win, 3-game winning streak

## Official KBO data path used
- `Schedule.aspx` -> locate the finished game entry and confirm the `gameId`
- `ws/Schedule.asmx/GetScoreBoardScroll`
  - Payload that worked for the summary block:
    - `leId=1`
    - `srId=0`
    - `seasonId=2026`
    - `gameId=20260530SKHH0`
  - Returned a usable score summary object with final score, venue, crowd, and team records.
- `ws/Main.asmx/GetKboGameList`
  - Useful for verifying the game entry and starter IDs.
  - For this game it exposed the starting pitchers directly in the game object:
    - Hanwha starter: `류현진` (`T_PIT_P_ID=76715`)
    - SSG starter: `김건우` (`B_PIT_P_ID=51867`)

## Box score / review endpoint note
- `ws/Schedule.asmx/GetBoxScoreScroll` returned a format error for this session when called directly with the same game context.
- Do not block the review card on that endpoint if the scoreboard summary and article review copy are already sufficient.
- If box score is needed, retry with the exact page-origin parameters rather than assuming the first call shape is correct.

## Photo sourcing note
- For this session, a strong editorial action shot from SportsChosun was used as the hero image rather than a static headshot.
- The selected hero image was a pitching action frame (`2026053001001824300122393_w.jpg`) because it read cleanly at card size and matched the review story better than the other candidates.
- Candidate image validation pattern:
  - fetch image URL directly
  - confirm `200`
  - confirm non-zero bytes
  - inspect rendered crop for readable subject and balanced composition

## Layout note
- The best-performing review layout was a compact light card:
  - left: single hero photo
  - right: summary + key stats + turning points
  - bottom: harvest / homework chips
  - footer: concise source line
- The final card looked better after reducing excess vertical whitespace.

## Copy note
- Keep the copy fact-first and short.
- Use only game facts, turning points, and postgame takeaways.
- Avoid editorial/meta commentary inside the card text.
