# YouTube image-summary pattern

Use this when the user shares a YouTube link and asks for the result **as an image** rather than a text summary.

## Proven workflow

1. Fetch transcript with the normal helper script first.
2. If `youtube-transcript-api` says `No transcript found`, probe with:
   ```bash
   yt-dlp --list-subs "URL"
   ```
3. If auto-captions exist, download `ko` / `ko-orig` (or the best available language) as VTT with `yt-dlp`.
4. Clean the VTT:
   - strip timing markup / inline tags,
   - collapse whitespace,
   - dedupe rolling-caption repeats where a longer line supersedes the previous shorter one.
5. Pull metadata with `yt-dlp --print` so the infographic can include title / channel / upload date / duration / chapter hints from the description.
6. Summarize into this compact Korean structure:
   - 한 줄 결론
   - 핵심 포인트 4~6개
   - 영상 흐름 3구간
   - 현실 조언 vs 의견/홍보 프레이밍
   - target-reader takeaway
7. Render as a bright Korean-first HTML infographic, then screenshot to PNG and visually verify:
   - Korean readability
   - bottom not clipped
   - all sections visible
   - no card overlap

## Notes

- This pattern works especially well for business / finance / creator-economy videos where the user wants not just summary but also a quick **판단 포인트**.
- Auto-captions are often good enough for the structure above, but small numbers / proper nouns may need caution labels.
- When the later part of a video shifts into course/event promotion, call that out explicitly instead of blending it into the factual summary.
