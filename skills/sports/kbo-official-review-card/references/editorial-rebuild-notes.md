# Editorial rebuild notes for KBO review cards

This note captures the session where the user corrected the review-card style and asked to rebuild the image, not just update the skill.

## Durable lessons

- If the user says the previous image still looks unchanged, do **not** resend the old PNG.
- Re-render the card from the newly updated HTML and deliver the new `MEDIA:` path.
- For review cards, the revised preference is:
  - 기사형 / 신문기사풍 feel
  - action-shot / 경기장면 photos over 증명사진-like headshots
  - main player or winning pitcher larger than secondary cards
  - clean crop, readable subject, no awkward empty margins
- Verification sequence that worked:
  1. build HTML
  2. open in browser
  3. confirm all important images load with `document.images`
  4. visually inspect the screenshot
  5. copy the actual rendered screenshot into `~/.miho/media_cache/`
  6. send that new file path

## Session-specific filenames

- HTML: `~/.miho/assets/kbo-cards/2026-05-29/hanwha_review_20260529_editorial.html`
- Final PNG: `~/.miho/media_cache/hanwha_review_20260529_editorial.png`

## Practical reminder

When the user asks to "redo it according to the edited skill", treat that as a request to regenerate the artifact with the new style constraints, not as a request to simply update the instructions.