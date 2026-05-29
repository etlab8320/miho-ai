---
name: sports-report-card
description: Create polished Korean sports preview/review images as HTML-first report cards, then render and send them as native media.
version: 1.0.0
platforms: [linux, macos, windows]
metadata:
  miho:
    tags: [sports, report-card, html-render, infographic, korean, discord-media]
    related_skills: [kbo-game-analysis, baoyu-infographic, claude-design]
---

# Sports Report Card

Use this skill when the user asks for a sports preview, review, recap, or prediction as an image.

This is the visual layer. Pair it with a domain analysis skill such as `kbo-game-analysis` for facts and judgment.

## Output rule

Create the report as HTML/CSS first, render it to a PNG, inspect it, then send it with `MEDIA:<path>`.

Do not make a plain matplotlib chart, spreadsheet-looking figure, or low-density text screenshot unless the user explicitly asks for that.

## Required workflow

1. Verify current game facts with official or reliable sources.
2. Gather visual assets:
   - Use key player or stadium photos when a reliable, usable source is available.
   - Prefer team/player official pages or reputable news images.
   - If image rights or source quality is unclear, use team colors, jersey-number typography, silhouettes, or clean stat modules instead of fabricating photos.
3. Build a single HTML canvas:
   - Default size: `1080x1350` portrait for Discord/mobile.
   - Alternative: `1600x900` landscape when the user asks for wide image.
   - Use CSS grid, strong hierarchy, and stable fixed dimensions.
4. Typography:
   - Korean default: Goyang, Pretendard, Noto Sans KR, Apple SD Gothic Neo, sans-serif.
   - Use tabular numerals for scores, innings, ERA, AVG, and win probabilities.
   - Do not let Korean text overflow boxes.
5. Visual structure:
   - Top: league/date/matchup and final score or start time.
   - Hero: winning/featured team signal with 1-2 key player photo slots.
   - Middle: 3-5 key moments or matchup keys.
   - Bottom: stat strip, next game note, and small source/date line.
6. Render to PNG under Miho media cache, usually `~/.miho/media_cache/`.
7. Inspect the PNG with vision or screenshot review:
   - Korean text rendered correctly.
   - No clipped text.
   - Player photos are not stretched.
   - Score and teams are immediately readable.
   - No overlap between inning lines, footnotes, or bottom labels.
8. Send the image as native media:

```text
MEDIA:/absolute/path/to/report.png
```

## Style direction

밝고 트렌디한 스포츠 매거진 / 스포츠신문 1면 감성으로. 젊고 세련되게.
A bright, trendy sports-magazine cover — NOT a dark, heavy broadcast card.

- **밝은 베이스가 기본** (화이트/크림/연한 톤). 어두운 배경은 사용자가 명시적으로 요청할 때만 — 기본은 밝게.
- **비비드한 팀 컬러 액센트** + 큰 임팩트 타이포 (스코어·팀명은 크고 대담하게). 칙칙·어두운 톤 지양.
- **키 플레이어 사진을 크게** — hero에 1~2명 사진 슬롯을 시원하게 배치. 사진 위에 팀 컬러 그라데이션 오버레이를 깔아 텍스트 가독성 확보 (트렌디 스포츠카드 표준 기법).
  - 안전하게 쓸 사진 소스가 없으면 사진을 지어내지 말고 팀 컬러 그라데이션 + 등번호/이름 대형 타이포 + 실루엣으로 대체 (그래도 충분히 임팩트 있게).
- 충분한 여백 + 모던 그리드. cute decoration 말고 editorial 한 밀도.
- 마무리 느낌: "스포츠신문 1면처럼 임팩트 있고 젊고 트렌디" — 30대 이하가 봐도 세련됐다고 느끼게.

## Example

`example-trendy.html` 은 목표로 하는 밝고 트렌디한 룩의 레퍼런스다 (KBO 경기 리뷰 카드).
밝은 크림 베이스 + 비비드한 팀 컬러 + 큰 임팩트 타이포 + 등번호 워터마크형 키플레이어 카드.
이 톤·레이아웃 감각을 참고하되, **점수·선수·기록 데이터는 매 경기 실제 값으로 교체**하고 예시의 값을 절대 재사용하지 마라.

## Postgame review layout (풍부한 리뷰)

경기 리뷰 카드는 스코어만 말고 아래를 충실히 담는다 (참고: example-trendy.html 톤 + 이 구조):
- 헤드라인 + FINAL 스코어
- 한 줄 총평 (cold read — 경기를 가른 핵심)
- 득점 흐름 또는 이닝 박스스코어 (확인된 데이터만; 모르는 이닝은 비워두고 지어내지 않는다)
- 승부가 갈린 장면 3~4개 (번호로)
- 키 플레이어 카드 3~4명 (역할 태그 WIN/POWER/CLUTCH/KEY + 이름 + 핵심 기록)
- 마운드 운영 (선발/불펜 핵심)
- 수확과 숙제 (사실에 근거한 짧은 논평)
- 출처/날짜/다음 경기

## Guardrails

- 점수·기록·라인업·부상·발언은 절대 지어내지 않는다. 확인된 출처의 값만 쓴다.
- 선수 사진: 사용자의 개인 용도면 공개된 선수/팀 사진을 적극 활용해도 된다 (소스가 있으면 박는다). 다만 "그 선수가 맞는" 사진만 — 엉뚱한 사람/합성/조작은 금지. 안전한 사진이 없으면 등번호·이름 대형 타이포 + 팀컬러 그라데이션으로 대체한다.
- 예측 요청 시 확신은 범위로 표시하고 단정하지 않는다.
- 사용자가 이미지를 명시 요청하면 속도보다 품질이 우선.
