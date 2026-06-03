---
name: html-infographic-rendering
description: Create polished information-summary images by designing a self-contained HTML infographic, then rendering it to PNG for chat delivery.
version: 1.0.0
platforms: [macos, linux, windows]
metadata:
  miho:
    tags: [html, infographic, image-rendering, korean, visual-summary, report-card]
    related_skills: [claude-design, baoyu-infographic, architecture-diagram]
---

# HTML Infographic Rendering

Use this skill when the user asks for a visual summary, architecture/relationship map, upgrade overview, report card, one-page explainer, or Discord-ready image and wants the result as an image. Build the artifact as HTML first, then render it to PNG.

## User-facing design preferences observed

When the user asks for a Miho/system summary image:

- Prefer a bright, clean background. Avoid dark backgrounds unless explicitly requested.
- Use Korean-first typography. Prefer `Goyang` / `고양체` in CSS, then fall back to Apple/Noto Korean fonts.
- Minimize coding-language jargon. Explain relationships, roles, strengths, risks, and future direction in plain Korean.
- Make the canvas large if needed. Do not omit important content just to fit a small card.
- Include a relationship map, not just bullet summaries.
- Deliver the PNG as native media and keep the HTML source path for later edits.
- For academy-owner / principal-facing promo material, write for non-technical readers first: explain what Miho does in practical 업무 language rather than architecture jargon.
- Avoid temporary state callouts such as “currently in progress”, worktree status, or internal update notes unless the user explicitly asks for a build/status report.
- Prefer completed, present-tense positioning over transition language like “becoming” / “getting closer to”. Present Miho as a finished capability set unless the user wants a roadmap slide.
- If the user asks for a Miho profile/character image, do not fake it with a quick SVG placeholder when a real image-generation path is available; generate an actual portrait and place it as a profile card or dedicated visual block.
- For Miho promo images, default the character direction to a beautiful, mature, anime-style woman with subtle Korean / gumiho cues when the user asks for a Miho personification. If the user asks for stronger 한국풍 or 여우 느낌, push hanbok-inspired styling, fox-like eyes, elegant ornaments, and refined Korean motifs rather than generic fantasy styling.
- When the user asks for a full-frame promo image, fill the *entire canvas* with content. Do not just shrink cards; add density at the canvas level with hero facts, supporting chips, and stronger visual anchors so large empty bands disappear.
- If the composition still feels empty after section trimming, fix it by restructuring the layout and adding content, not by further reducing card height alone.
- For moonlit Miho branding, use a visible dark hero area plus a portrait or character block so the image reads as "미호AI" with a distinct identity rather than a generic AI dashboard.

## Miho promo-card refinement

For Miho product-introduction or promo cards:

- Keep the **MihoAI** brand name visually dominant; the product name should read first.
- Short, promotional copy works better than literal explanatory copy.
- If the user wants a “달 아래 구미호” vibe, keep moon/night/fox imagery visible in the layout and not just implied by the copy.
- Avoid leaving the hero/header and profile areas too tall or empty; reduce vertical whitespace when the user says the page feels “휑해”.
- When the user says sections overlap, verify the live layout visually and with DOM measurements before changing text or spacing.
- Prefer a strong profile image plus small keyword chips/badges over an empty-looking hero block.
- Compress the bottom card sections if the page feels too tall; remove unnecessary padding before adding more content.
- If a profile image looks too generic, pick a portrait with a mature, elegant, Korean/gumiho feel and better contrast with the dark hero background.
- When the user asks for a **full-frame** promo image, fix emptiness at the canvas level instead of only shrinking cards. Rebalance the whole composition so top, middle, and bottom feel equally dense.
- Keep the **spacing rhythm** consistent: top section gap, middle section gap, and bottom section gap should feel like the same design system, not random whitespace.
- If a section feels weak, add a few large, high-signal proof points or chips rather than many small lines of text. The user prefers **큰 글씨, 짧은 문구, 강조 중심** over dense paragraph blocks.
- If the right/profile side feels empty, make it a true card with a matching visual weight to the left header, not a loose image slot.
- If the user calls out "검정 투명" / "투명해 보임" / "뒤가 비침", remove overlay layers first. The profile block should read as one opaque card, not a stacked translucent panel.
- When the profile card needs a mood image, keep the image inside the card boundary and avoid extra glow/gradient layers that make the card feel see-through.
- If the background mood matters, keep the moon/fox/night art visible in the composition and tune the profile image to match it.
- If the user says the bottom feels empty, reduce unused lower whitespace and add compact tag rows or closing highlights instead of only resizing the bottom cards.
- For **weekly health reports**, prefer a **full-page report layout** over a small card layout: a headline, summary chips, a top-row KPI strip, a big weight trend chart, a calorie bar chart, a blood-pressure panel, daily log rows, and a closing weekly verdict. The user explicitly prefers a report feel over a card feel.
- For weekly report charts, use 5–7 day trends rather than single-day highlights. Weight should be a line chart, calories a bar chart, and blood pressure a simple gauge/point display that only appears on days it was actually measured.
- For weekly health reports, verify the live HTML first, then render. Open the HTML in a browser or headless Chrome, inspect the layout, and only then edit/render again. Do not trust CSS assumptions when the user is asking about legibility.
- For weekly health routine images requested on Monday, use a **single report-style page** with recent weight, blood sugar/blood pressure routine, and 월~토 meal/exercise blocks rather than a loose stack of daily cards. See `daily-health-image-card/references/weekly-routine-brief.md` for the session-specific brief.
- If the user asks to add one field to an existing scheduled health image (for example, total calories), patch the existing cron/image workflow instead of generating a separate standalone redesign unless they explicitly ask for a new concept.
- Before final delivery, render and visually verify the PNG at a viewport tall enough to include the complete report. If any gray footer or blank band remains, increase or decrease the canvas/screenshot height and re-check before shipping.
- Treat a weekly report as a narrative summary, not a pile of day cards. Compress each day into one line and reserve larger visual weight for the charts and summary verdict.

- For profile cards that still look translucent after CSS changes, verify the rendered PNG again before touching typography or spacing. The fix is usually to simplify the card layers, not to add more decoration.

- Prefer completed, present-tense positioning over transition language like “becoming” / “getting closer to”. Present Miho as a finished capability set unless the user wants a roadmap slide.
- If the user asks for a Miho profile/character image, do not fake it with a quick SVG placeholder when a real image-generation path is available; generate an actual portrait and place it as a profile card or dedicated visual block.
- For Miho promo images, default the character direction to a beautiful, mature, anime-style woman with subtle Korean / gumiho cues when the user asks for a Miho personification. If the user asks for stronger 한국풍 or 여우 느낌, push hanbok-inspired styling, fox-like eyes, elegant ornaments, and refined Korean motifs rather than generic fantasy styling.
- For product-promo copy, make the product name the anchor (`미호AI` first and largest when appropriate). If the user dislikes a metaphor or tagline, replace it with a punchier promotional line rather than defending the original wording.
- Treat overlap complaints as a rendering problem first, not a copy problem. Verify with browser visual inspection and box measurements; don’t assume the DOM layout is fine because the CSS looks plausible.
- If the hero/card area reads too empty, tighten the title box and add high-signal elements such as chips, a portrait, or a short proof-point row so the emptiness looks intentional instead of unfinished.
- For Miho-branded promo pieces, make **미호AI** the primary product name in the visual hierarchy. Use it in the headline and in at least one supporting label/card so the brand reads instantly.
- If the user wants a gumiho identity in the copy, express it naturally through traits like **구미호의 감각, 맥락을 읽는 힘, 예리한 판단, 끝까지 처리하는 실행력**. Avoid gimmicky or awkward slogan construction.

## Workflow

1. Gather grounded facts first.
## Workflow

1. Gather grounded facts first.
   - Use `git log`, `git status`, config snippets, service status, workspace indexes, or other project facts as appropriate.
   - Do not rely only on memory for current state.
2. Decide the narrative.
   - Top verdict: what changed and why it matters.
   - Relationship map: users/platforms → gateway → memory/RAG → core agent → work/Kanban → future direction.
   - Capability blocks: strengths, current stability, risks, roadmap.
   - For promo/explainer images aimed at academy owners or other non-technical stakeholders, translate internal systems into simple operational language: “찾고 정리하고 바로 전달” beats “vector retrieval / subagents / pipeline orchestration”.
3. Write one self-contained HTML file.
   - Inline CSS.
   - Use a fixed large canvas width (e.g. 1800px) for reliable rendering.
   - Use bright paper tones, soft borders, readable hierarchy, and restrained accents.
   - CSS font stack example:
     ```css
     font-family: 'Goyang','GoyangIlsan','Apple SD Gothic Neo','Noto Sans KR',sans-serif;
     ```
   - If a character/profile visual is requested, reserve a clear card area for it instead of hiding it as a faint decorative background.
   - If the user wants the portrait to read like a real profile photo, use an actual generated image asset, not a vector stand-in. When the generic `image_generate` tool is unavailable but the OpenAI Codex image-gen plugin is installed, generate through the `openai-codex` provider path and then insert the saved local image.
   - For profile cards, leave generous breathing room around the portrait request itself (e.g. ask for the whole upper torso to fit) so the inserted image can use `object-fit: contain` without losing the subject.
   - For Miho promo art, keep the brand name explicit in the headline and preserve the moon/fox/night identity; the user often prefers a direct, magnetic line such as `당신을 홀리는` over softer metaphorical wording.
- If the user says the image should “fill the frame,” do not only resize individual cards. Rebalance the whole canvas: hero area, middle section, and lower section must be tuned together.
- Keep the top / middle / bottom spacing rhythm consistent. Uneven gaps between sections read as a layout bug, even if each card looks good in isolation.
- If the user asks for larger text, increase the actual font sizes of titles, labels, and key chips. Do not fake it with only bolder weight or more padding.
- If the user says the image should feel less empty, add density inside the hero section with compact facts/chips and stronger anchors rather than merely shrinking the card height.
- For recurring health summaries, keep **daily** and **weekly** artifacts separate: the daily version should stay concise, while the weekly version should become a report-style overview with charts.
- For portrait cards, verify the image is integrated into the mood system, not left as a floating placeholder. The profile area should look like a real card with matching weight, not a loose image slot.
- When the background mood matters, keep the moon/fox/night art visible and choose a portrait that matches it. Avoid generic dark/black backgrounds unless the user explicitly wants that look.
- For academy-facing promo art, keep the copy user-facing and operational. If the visual is about academy workflows, include real anchors like PACA / Peak rather than developer jargon.
- If the user later resets the same artifact to a **generic product-introduction** image, remove academy/domain anchors again. Do not preserve terms such as 맥스, 체대입시, ET, 학원, 원장, 학생, PACA, Peak, 파카, or 피크 unless the latest instruction explicitly wants that domain positioning.
- When the user points to a specific earlier HTML file and says “여기에서 정리해,” treat that file as authoritative. Edit or fork from that exact source instead of continuing from the newest iteration.

   - macOS Chrome example:
     ```bash
     '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' \
       --headless=new --disable-gpu --hide-scrollbars \
       --window-size=1800,3600 \
       --screenshot=/path/output.png \
       file:///path/input.html
     ```
   - Increase the window height if the bottom is cut off.
5. Verify visually.
   - Load the PNG with vision/image inspection.
   - Check: no clipping, readable Korean, bright background, relationship map visible, summary sections complete.
   - Before final delivery, compare the page/document height against the screenshot viewport. For browser-rendered HTML, load the local file and inspect `document.documentElement.scrollHeight` / the main canvas height; if the screenshot height is shorter, re-render with a taller `--window-size` height.
   - If the first visual inspection shows the lower sections cut off, do not redesign blindly. Measure DOM height, re-render to at least that height plus a small margin, then inspect the full PNG again.
   - For profile cards, verify the inserted image is the intended generated asset, not a placeholder illustration.
   - Check the entire frame, not just one card: top-to-middle gap, middle-to-bottom gap, and whether the canvas feels filled rather than card-resized.
6. Final response.
   - Attach `MEDIA:/absolute/path/output.png`.
   - Include the HTML source path.
   - Briefly note what was verified.

## Pitfalls

- A visually attractive hero can still fail if the overall canvas feels sparse. Add small info cards/chips before shrinking the whole composition.
- Do not only tune section heights independently. Re-check the full frame after any canvas-height or grid-row change.
- If the user says the top and middle are too far apart, the fix is often a combined adjustment of hero height and content density rather than only reducing card size.
- For profile cards, a large empty media block reads as unfinished; fill it with image + short supporting chips or trim it aggressively.
- Always confirm that the brand name remains prominent. For Miho promo images, `미호AI` should be immediately visible.


## Pitfalls

- If the user says something is overlapping, verify the rendered HTML in a browser before changing copy again. Screenshot-by-code is not enough; inspect the live layout and the bounding boxes.
- Product-promo cards should not leave large unused hero regions. If the top section feels empty, reduce padding/min-height and add chips or an image before calling the design complete.

- Chrome screenshots capture the requested viewport height, not always the full document. If the bottom is cut off, measure the actual DOM height with `document.documentElement.scrollHeight` and re-render with a taller `--window-size` height.
- When a fixed canvas uses `min-height` but content extends beyond it, the initial screenshot may look fine at the top while silently omitting lower sections. Treat “visual check only saw the top” as a failure; inspect the full-height image after re-rendering.
- For weekly report layouts, avoid leaving a large blank lower band just because the canvas is tall enough. If the PNG shows too much empty space, shrink the canvas min-height and re-render until the composition feels intentionally full.
- For wide landscape infographics with dense Korean text, start larger than social-card size (for example 2400×1350 or 2800×1920) and verify at full image scale. If cards overlap or bottom rows clip, increase both the CSS canvas height and the Chrome `--window-size` height; do not merely increase the screenshot height while leaving fixed CSS grid rows too small.
- When using an existing Miho/profile/logo image as a background, keep it decorative and low-opacity so it does not compete with relationship-map text. A right/bottom placement works well for wide maps.
- If the user specifically asks for a visible profile portrait, do not leave it as a faint background element. Remove the decorative background treatment and place the portrait in an explicit card/slot.
- If the user says the portrait should fully fit inside the card, switch the inserted image treatment from cover-style cropping to a full-fit presentation (`object-fit: contain` or equivalent), add inner padding/background framing, and enlarge the card row if needed so the image and nearby stat cards do not collide.
- If a real generated portrait is requested, a handmade SVG stand-in is not an acceptable final asset unless the user explicitly asked for an illustration mockup.
- `Goyang` may not be installed on the host. Still specify it first in CSS, then robust Korean fallbacks.
- Avoid turning the image into a code audit. For executive or user-facing summaries, replace file/function names with concepts unless the user asks for implementation detail.
- Do not claim visual verification unless you actually loaded the rendered image or otherwise inspected it.

## References

- `references/miho-landscape-map-rendering.md` — notes from a Miho update-map session: wide canvas sizing, background profile image treatment, clipping fixes, and using a real generated portrait instead of a placeholder when the user asks for a Miho profile visual.
- `references/miho-profile-card-portrait-notes.md` — owner-facing promo-image lessons: Korean/gumiho portrait direction, using Codex-backed real image generation, and making the full upper-body portrait fit the profile card cleanly.
- `references/miho-product-intro-layout-notes.md` — session notes on Miho product-intro wording, brand prominence, moon/fox mood, and spacing fixes the user asked for repeatedly.
- `references/miho-promo-layout-overlap-notes.md` — this session’s layout lessons: hero-height trimming, brand prominence, and browser-based overlap verification.
- `references/miho-promo-title-and-overlap-checks.md` — product-name-first copy, user-facing tone fixes, and browser/vision verification steps for catching title prominence and section overlap before final delivery.
- `references/miho-generic-promo-copy-notes.md` — generic Miho product-introduction copy rules: remove owner/domain anchors, avoid corny assistant slogans, use benefit-led phrasing and colored emphasis.
- `references/miho-full-frame-promo-lesson.md` — this session’s full-frame lesson: rebalance the entire canvas, keep section gaps consistent, and add density with chips/facts instead of shrinking cards alone.
- `references/miho-promo-layout-qa.md` — compact QA notes from the Miho promo-image tuning session: spacing rhythm, profile-card weight, larger text, and academy/PACA-Peak anchors.
- `references/miho-v11-product-intro-reset.md` — lesson from resetting a MihoAI promo image back to an earlier HTML source: product-name-first hierarchy, generic product copy, and removing domain anchors when requested.
- `references/health-weekly-report-lesson.md` — weekly-vs-daily health report lesson: report-style layout, chart selection, and screenshot-height verification to avoid blank lower bands.

## Output paths

For Miho-related media, a useful default is:

```text
~/.miho/media_cache/<topic>/<artifact>.html
~/.miho/media_cache/<topic>/<artifact>.png
```
