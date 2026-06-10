# Academy Hakjong Report Package Spec

## Problem
학생부종합전형 PDF가 스킬 지시만 믿고 생성되면서 로고, 푸터, A4 방향, 페이지 수, 학생명 일치가 흔들렸다.

## Scope
### In
- 학종 PDF 전달 전 검증·패키징 도구 추가.
- 통과한 PDF만 `~/.miho/media_cache/susi_student_record/validated`로 승격.
- `media_tag` 반환으로 Discord 첨부 안전망을 사용.
- 생기부/학종 근거 도구 사용 증거와 페이지별 PNG/contact sheet를 요구.
- 모든 리포트가 같은 MAX 학원 브랜드 시스템에서 나온 것처럼 보이도록 템플릿 아이덴티티와 카드 밀도를 검증한다.
- `student_stage`별 리포트 목적을 검증한다.

### Out
- 자연어 라우터에 특정 키워드 분기 추가.
- PDF 본문 생성 자동화 전체 재작성.

## Acceptance Criteria
- locked `premium_hakjong_report` 마커가 없으면 실패한다.
- `maxReport`, `reportIdentity`, `sectionDeck`, MAX 색상 토큰, 한국어 줄바꿈 CSS가 없으면 실패한다.
- 카드형 분석 블록이 6개 미만이거나 긴 글덩어리 섹션이 있으면 실패한다.
- `student_stage`가 없거나 학년/상태별 목적과 본문이 맞지 않으면 실패한다.
- 1학년은 상담에서 확인한 관심사·학교생활 기반의 생활기록부 시작 설계여야 한다.
- 2학년은 1학년 기록/상담 맥락을 이어 2학년 선택과목·동아리·진로활동 설계로 연결해야 한다.
- 3학년은 1학기 입력 전 과세특·세특·진로활동·행특 보완과 지원 가능성 판단을 포함해야 한다.
- N수생/졸업생은 완성된 학생부 분석, 지원 가능성 판단, 면접 방어/설명력 중심이어야 한다.
- A4 가로형, 4페이지 불일치, wrong branding, 학생/학교/학과/전형 불일치면 실패한다.
- 1/2학년은 상담·학생맥락 근거와 학종/입시 프로파일 근거가 필요하고, 3학년/N수생은 `life_record_*` 근거와 학종/입시 프로파일 근거가 필요하다.
- 페이지별 PNG 수가 PDF 페이지 수와 다르거나 contact sheet가 없으면 실패한다.
- PDF/HTML 본문에 `자료 기준`, `생활기록부 데이터`, `공식 전형자료`, `맥스 수시엔진 산출 데이터`, `AI`, `프리미엄` 같은 운영/제작/홍보성 문구가 있으면 실패한다.
- 음수 자간, 굵은 좌우 강조선, absolute footer 같은 생성형 템플릿 흔적이 있으면 실패한다.
- 성공 결과는 `ok:true`, `file_path`, `manifest_path`, `media_tag`를 포함한다.
- 실패 결과는 `ok:false`이며 `media_tag`를 포함하지 않는다.

## API Contract
- Tool: `academy_hakjong_report_package`
- Required: `html_path`, `pdf_path`, `student_name`, `university_name`, `student_stage`, `evidence_tools`, `page_image_paths`, `contact_sheet_path`
- Optional: `department_name`, `track_name`, `expected_pages`

## Test Plan
- 정상 locked HTML/PDF 검증 성공.
- 기존 실패 유형처럼 템플릿 마커가 없으면 실패.
- landscape PDF 메타면 실패.
- plugin.yaml 등록 목록과 런타임 등록 목록 일치.
