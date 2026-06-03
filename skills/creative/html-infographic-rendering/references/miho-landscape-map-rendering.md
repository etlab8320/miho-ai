# Miho landscape map rendering notes

## Audience + tone

For academy-owner / principal-facing promo images:

- Explain Miho in practical 업무 language, not internal AI architecture terms.
- Prefer present-tense completion framing ("미호는 …입니다") over transition framing ("가까워졌다", "이제 …이 되어간다").
- Remove internal progress/status notes unless the user explicitly wants an engineering status board.
- If the user says the audience is non-technical, simplify every section title and body copy accordingly.

## Layout lessons

- Wide Korean infographics clip easily if the CSS canvas height and the screenshot height drift apart. Increase both together.
- If a profile portrait is requested, it should occupy a clear top-side card or dedicated slot — not a barely visible decorative background.
- When a background profile image is reported as invisible, the right fix is often to change placement strategy entirely rather than only increasing opacity.

## Profile portrait lesson

A hand-drawn SVG placeholder may be acceptable for mockups, but not when the user explicitly asks for an attractive Miho profile image.

Preferred path when available:

1. Generate a real portrait asset first.
2. Visually inspect the generated image for age/tone/style fit.
3. Insert that asset into the HTML card with `object-fit: cover` and top-centered cropping.
4. Re-render and visually verify that the portrait card reads as intentional, not decorative filler.

## Codex-auth image generation note

In this session, the standard `image_generate` tool still tried the FAL backend even after enabling `image_gen/openai-codex`, likely because plugin enablement takes effect on the next session.

Useful workaround when Miho already has Codex/ChatGPT OAuth available:

- Import `plugins/image_gen/openai-codex/__init__.py` directly.
- Instantiate `OpenAICodexImageGenProvider()`.
- Call `provider.generate(prompt=..., aspect_ratio='portrait')`.

This produced a usable portrait immediately and avoided waiting for a new session.

Use this as a tactical workaround for the current session only; prefer the normal `image_generate` path in fresh sessions once the provider is active.

Additional Codex stream pitfall observed: the OpenAI Python streaming parser may raise `TypeError: 'NoneType' object is not iterable` after emitting `response.image_generation_call.partial_image` events. If this happens, collect the latest `partial_image_b64` during the stream, save it manually as PNG, and avoid relying only on `stream.get_final_response()` for the final image.
