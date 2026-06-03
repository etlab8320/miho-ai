# Miho promo title and overlap checks

Session lessons for Miho-facing promo infographics.

## Copy rules

- Put **미호AI** in the primary visual hierarchy first. The product name should appear in the headline or eyebrow, not only in a secondary badge.
- Keep the main promise in plain promotional language. Avoid vague metaphor-first wording that hides the product name.
- If the user asks for a more seductive line, use it directly and keep it short. Do not over-explain the metaphor.
- Prefer product-intro phrasing over developer phrasing. The copy should read like marketing, not system notes.

## Layout checks

- Verify the rendered page, not just the HTML.
- Use browser/vision inspection to check whether the top hero block and the next card row visually collide.
- If a section looks tight or overlapping, inspect DOM bounds and rerender with adjusted canvas height / grid row sizes.
- In the browser, the useful measurement pattern is:
  - title block bounding box
  - hero/profile card bounding box
  - main content top
  - bottom section top
- If the hero block visually intrudes into the next section, treat it as a layout defect even if the HTML technically flows.

## Practical lesson from the session

- A headline like “구미호의 감각처럼” read as too indirect for this user.
- A short, direct line like “당신을 홀리는” was preferred when the user explicitly wanted a stronger hook.
- “미호AI” must be visible as the brand anchor in the intro area and in the profile card.
