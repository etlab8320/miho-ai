# KBO Card Quality Rules

These rules capture the expected visual quality for Miho KBO image cards.

## Non-Negotiables

- Use a consistent white/light HTML template across follow-up cards.
- Use `원정`, never `방문`.
- Include previous-game result when useful and available.
- Do not show placeholder stat text such as `시즌기록 확인 필요` for known players.
- Do not send a card with broken image icons.
- Do not shrink dense content into tiny unreadable type; make the canvas taller.
- Do not place large scores over team names.

## Player Photos

- Key-player photos should be visible in the final Discord image.
- Prefer official player photos when player IDs are available.
- For review cards, action/news photos are preferred only when the source clearly matches the player/game.
- Embed photos as data URIs when possible so final screenshots do not depend on remote image loading.
- Verify with browser JavaScript before screenshot:

```js
Array.from(document.images).map(img => ({
  alt: img.alt,
  ok: img.complete && img.naturalWidth > 0,
  w: img.naturalWidth,
  h: img.naturalHeight
}))
```

Every important player image should be `ok: true`.

## Prediction Depth

Prediction cards should include cron-level depth, not a quick text-pick depth:

- Latest standings.
- W-L-D, win pct, games back, recent 10, streak, home/away.
- Team AVG, runs, HR, ERA, WHIP when available.
- Starter W-L, ERA, IP, WHIP, K/BB, recent starts, workload risk when available.
- Previous game score/result and practical context.
- Recent 5-10 game scoring/allowed trend when it affects the pick.

## Review Depth

Postgame review cards should include:

- Final score and inning table.
- R/H/E/B.
- HR, decisive hit, key inning, errors when relevant.
- Starter line and bullpen usage.
- WPA/key-player candidates when available.
- `수확` and `숙제` split, especially for Hanwha.

## Visual QA

Before sending:

- Open the HTML.
- Verify all images load.
- Render PNG from the HTML.
- Inspect the PNG.
- Confirm no bottom clipping on tall cards.
- Confirm Korean labels fit within their modules.
- Confirm the exact `MEDIA:` path points to the verified PNG.
