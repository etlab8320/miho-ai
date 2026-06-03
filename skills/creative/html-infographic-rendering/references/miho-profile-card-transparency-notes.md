# Miho profile-card transparency notes

## What the user corrected
- A dark profile card can still be wrong if it feels *translucent* or like a stacked overlay.
- The user wants the right/profile block to read as a **single opaque card**: no visible transparent black layer, no background bleeding through, no extra decorative overlay that makes the card feel split.

## Practical fix pattern
1. Remove any gradient overlay or radial glow that looks like a separate layer.
2. Make the card background a single opaque fill or a single background image layer.
3. Keep the image/background confined to the card; avoid effects that make the card seem see-through.
4. Re-render and inspect the actual PNG, not just the HTML/CSS.
5. If the card still looks translucent in vision, simplify again before changing spacing or typography.

## Verification cues
- The card should look like one block.
- The outer background should not appear to bleed into the card.
- If the user says "검정 투명" or similar, treat it as a hard visual defect, not a styling preference.
