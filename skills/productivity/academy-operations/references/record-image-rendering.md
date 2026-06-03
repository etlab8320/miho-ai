# Record image rendering checklist

Use this when 맥스 asks for event records “정리해서 이미지로 줘” or wants a Discord-ready visual table.

## Goal

Turn live Peak record data into a readable image, not a text dump.

## Preferred path — use the tool, don't hand-draw

이미지 표는 **`academy_report_image` 도구**로 만든다. execute_code로 직접 HTML/canvas를 그리지 말 것.

1. 라이브 기록을 먼저 가져온다.
2. 종목 의미에 맞는 정렬·강조 방향을 정한다 (거리/높이=클수록, 시간=작을수록). → 도구의 `columns[].best` 에 `high`/`low` 로 넘긴다.
3. `academy_report_image` 호출: `title`, `columns`(종목+단위+best), `groups`(필요 시 남학생/여학생, 각 `avg_label`), `rows`. 도구가 헤더↔값 정렬, 평균 계산, 디자인, 스탬프를 보장한다.
4. 전송.

## Design

- **밝고 트렌디한 라이트 톤이 기본.** 어두운 배경은 사용자가 명시적으로 요청할 때만 — 기본은 어둡게 하지 않는다.
- 색은 고정(하드코딩)하지 말고 밝은 트렌디 톤 안에서 고른다.
- 이미지 캔버스는 **내용에 맞게 컴팩트하게** 맞춘다. 불필요한 하단/외곽 여백을 남기지 말고, 보이는 크기는 작아도 읽기 쉽게 압축한다.
- rank/name/value 컬럼은 **헤더와 본문 모두 가운데정렬**을 기본으로 맞춘다.
- 행/열 정렬이 흐트러지지 않도록, 제목·헤더·본문·평균칩의 baseline과 padding을 먼저 맞춘 뒤 렌더한다.
- **제목/부제에 메타 설명을 덧붙이지 말고, 사용자 요청에 없는 ‘~만 따로 정리’ 같은 문구를 넣지 않는다.**
- **제목/부제에 메타 설명을 덧붙이지 말고, 사용자 요청에 없는 ‘~만 따로 정리’ 같은 문구를 넣지 않는다.**
- 제작 후에는 반드시 **비전 검수**로 잘림, 정렬 어긋남, 하단 overflow를 확인한다.
- rank/name/value 컬럼이 시각적으로 분명하게.

> 도구를 쓸 수 없는 예외 상황에서만 수동 렌더하며, 그때도 위 디자인 원칙(밝은 톤)과 가운데정렬 기준을 따른다.

관련 레퍼런스: `references/record-image-delivery-qa.md`
