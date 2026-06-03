# Miho profile-card portrait notes

Condensed lessons from a Miho promo-image session aimed at academy owners.

## What the user corrected

- Do not use temporary-status language like "currently in progress" in promo material.
- Do not frame Miho as "becoming" something; present it as a completed capability set.
- Explain Miho in simple owner-facing 업무 language, not internal architecture terms.
- A faint background logo/profile is not enough when the user asks for a Miho character image.
- A hand-drawn SVG placeholder is not acceptable when a real generated portrait path exists.
- When the user says the portrait should fit in the profile slot, the full portrait card must show the whole subject rather than cropping into the face.
- For Miho personification, the preferred direction is: beautiful, mature, alluring anime-style woman with Korean and subtle gumiho cues.

## Effective image prompt direction

Use prompts close to:

- mature adult Korean woman
- subtle gumiho vibe
- refined Korean traditional aesthetic
- hanbok-inspired styling details
- graceful fox-like eyes
- intelligent and magnetic expression
- upper torso fully visible
- centered composition with generous breathing room
- clean light background
- polished illustration, non-explicit

## Effective implementation pattern

1. Generate the portrait first as a standalone local image.
2. Verify the asset visually before insertion.
3. Put it in an explicit profile card near the top of the infographic.
4. If the card crops too much, switch to a framed full-fit treatment:
   - `object-fit: contain`
   - light inner background
   - padding inside the image frame
   - larger row height so the card does not overlap adjacent KPI cards
5. Re-render and visually verify the full infographic after each layout adjustment.

## Provider/tool note

If the generic `image_generate` tool is wired to a provider that is unavailable, but the OpenAI Codex image-gen plugin exists and Codex auth is present, use the `openai-codex` image provider path to generate the portrait and then insert the saved local file into the HTML.
