---
name: youtube-content
description: "YouTube transcripts to summaries, threads, blogs."
platforms: [linux, macos, windows]
---

# YouTube Content Tool

## When to use

Use when the user shares a YouTube URL or video link, asks to summarize a video, requests a transcript, or wants to extract and reformat content from any YouTube video. Transforms transcripts into structured content (chapters, summaries, threads, blog posts).

Extract transcripts from YouTube videos and convert them into useful formats.

## Setup

```bash
pip install youtube-transcript-api
```

## Helper Script

`SKILL_DIR` is the directory containing this SKILL.md file. The script accepts any standard YouTube URL format, short links (youtu.be), shorts, embeds, live links, or a raw 11-character video ID.

```bash
# JSON output with metadata
python3 SKILL_DIR/scripts/fetch_transcript.py "https://youtube.com/watch?v=VIDEO_ID"

# Plain text (good for piping into further processing)
python3 SKILL_DIR/scripts/fetch_transcript.py "URL" --text-only

# With timestamps
python3 SKILL_DIR/scripts/fetch_transcript.py "URL" --timestamps

# Specific language with fallback chain
python3 SKILL_DIR/scripts/fetch_transcript.py "URL" --language tr,en
```

## Output Formats

After fetching the transcript, format it based on what the user asks for:

- **Chapters**: Group by topic shifts, output timestamped chapter list
- **Summary**: Concise 5-10 sentence overview of the entire video
- **Chapter summaries**: Chapters with a short paragraph summary for each
- **Thread**: Twitter/X thread format — numbered posts, each under 280 chars
- **Blog post**: Full article with title, sections, and key takeaways
- **Quotes**: Notable quotes with timestamps

### Example — Chapters Output

```
00:00 Introduction — host opens with the problem statement
03:45 Background — prior work and why existing solutions fall short
12:20 Core method — walkthrough of the proposed approach
24:10 Results — benchmark comparisons and key takeaways
31:55 Q&A — audience questions on scalability and next steps
```

## Workflow

1. **Fetch** the transcript using the helper script with `--text-only --timestamps`.
2. **Validate**: confirm the output is non-empty and in the expected language. If empty, retry without `--language` to get any available transcript. If still empty, tell the user the video likely has transcripts disabled.
3. **Chunk if needed**: if the transcript exceeds ~50K characters, split into overlapping chunks (~40K with 2K overlap) and summarize each chunk before merging.
4. **Transform** into the requested output format. If the user did not specify a format, default to a summary.
   - If the user asks for an **image summary**, pair this skill with an HTML/PNG rendering workflow rather than pasting long text. A reliable Korean-first structure is:
     1. one-line verdict,
     2. 4-6 key points,
     3. 3-part chapter flow with approximate timestamps,
     4. critical reading (`사실/설명` vs `의견/홍보/과장`),
     5. one actionable takeaway for the target reader.
   - For short videos, this structure produces a compact Discord-ready infographic without losing the distinction between grounded content and promotional framing.
5. **Verify**: re-read the transformed output to check for coherence, correct timestamps, and completeness before presenting.

## Error Handling

- **Transcript disabled**: tell the user; suggest they check if subtitles are available on the video page.
- **Private/unavailable video**: relay the error and ask the user to verify the URL.
- **No matching language**: retry without `--language` to fetch any available transcript, then note the actual language to the user.
- **Dependency missing**: run `pip install youtube-transcript-api` and retry.

## Fallback for auto-captions missing from youtube-transcript-api

Some videos return `No transcript found` from `youtube-transcript-api` even though YouTube exposes **automatic captions**. Before giving up:

1. Probe subtitle availability with:
   ```bash
   yt-dlp --list-subs "URL"
   ```
2. If automatic captions exist (for example `ko` / `ko-orig` / `en`), download them directly:
   ```bash
   tmpdir=$(mktemp -d)
   yt-dlp --skip-download --write-auto-sub --sub-lang ko --sub-format vtt \
     -o "$tmpdir/%(id)s.%(ext)s" "URL"
   ```
3. Read the `.vtt` file, strip timing tags / inline markup, and dedupe the repeated rolling-caption lines before summarizing.
4. If the user wants an image summary, this cleaned auto-caption text is usually good enough to drive a grounded infographic, but explicitly note that fine-grained numbers / names may need re-checking because auto-captions can be noisy.

This fallback is especially useful for Korean YouTube videos where auto-captions are available through YouTube but not exposed cleanly through the transcript API.

## References

- `references/youtube-image-summary-pattern.md` — compact workflow for turning transcript + metadata into a Korean infographic image, including the reality-vs-promo framing pass and visual verification checklist.
