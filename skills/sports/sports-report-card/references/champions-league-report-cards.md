# Champions League Report Cards

Session note: when the user says `챔스` or asks for a Champions League review/report image, treat it as a sports report-card task, not a text-only recap.

## Grounded facts workflow

Use a reliable live match page with accessible text content when possible. In this session, ESPN’s match page exposed the needed review data directly in page text and browser console:

- final score / ET / penalty shootout status
- match stats such as possession, shots on goal, shot attempts, corners, saves, yellow cards
- timeline items for goals, cards, and penalty events

Recommended extraction pattern:

1. Open the match page.
2. Use browser text or console inspection to pull the summary, match commentary, and stats block.
3. Verify the scoreline and shootout result against the page title/summary.
4. Build the card with a clear editorial layout: team panels, central verdict, turning points, and a stats grid.

## Report-card layout preferences for Champions League

- Use a bright editorial look, not a dark broadcast slate.
- Put the final score and result in the center, large and unmistakable.
- Keep the winning side visually emphasized, but do not bury the losing side.
- Include 3 decisive moments only; do not overload with commentary.
- Show a penalty shootout note if the match ended AET/PKs.
- If logos are available and reliable, use them as the primary team visuals.
- Keep the footer small and unobtrusive.

## Good source cues

Prefer pages that expose one or more of these in readable text:

- match title containing the final score
- summary block with final result
- commentary lines for the key goals / penalty events
- match stats block with possession, shots, corners, saves, cards

If the live page is noisy, use the page’s own match summary and stats rather than a second source unless you need a quick cross-check.