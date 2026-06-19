# 미호 2027 수시 체대 계산 운영 가이드

작성일: 2026-06-20

## 목적

미호AI가 "학생 생기부로 2027 수시 체대 실기전형 추천" 또는 "특정 학교 내신환산점수 계산"을 수행할 때 따라야 할 최종 기준이다. 이 문서는 산식 검증 라운드, 클로드/코덱스 교차검증, OCR 재판독 결과를 합친 운영용 잠금 문서다.

## 절대 기준

- Ground truth는 2027 수시모집요강 PDF 원문이다.
- 수시엔진은 작년 최종합격자 총점 비교용이다. 내신환산 산식 검증이나 계산식 기준으로 쓰지 않는다.
- 미호 계산은 `plugins/susi_ops/formula_adapter.py`가 로드하는 공식 산식 런타임을 우선한다.
- 같은 학교에 개별 산식과 통합 산식이 있으면 추천/개별계산 모두 동일 런타임 경로를 타야 한다.
- PDF 텍스트 추출본은 검색 보조다. OCR 품질이 낮은 학교는 PDF 이미지 판독 기록을 우선한다.

## 운영 경로

### 추천 요청

사용자가 "박시현 수시 실기전형 추천해줘"처럼 묻는 경우:

1. `plugins/susi_ops/recommendation.py::recommend_candidates`
2. 중앙 생기부 DB에서 학생 성적/출결 로드
3. `plugins/susi_ops/targeting.py`로 체대 추천 대상 필터
4. `plugins/susi_ops/formula_adapter.py`로 공식 산식 플러그인 계산
5. 전년도 최종합격자 총점은 비교 기준으로만 결합

지역은 필수다. 사용자가 이미 말한 지역이 있으면 그대로 `region`에 넣고, 없으면 지역만 물어본다.

### 개별 학교 계산

사용자가 "박시현 경기대 내신환산점수 계산해줘"처럼 묻는 경우:

1. 같은 학생 성적/출결 소스 사용
2. 같은 공식 산식 런타임 사용
3. 결과에는 학생부 환산점수, 학생부 만점, 실기 만점, 총점 구조를 함께 보여준다.

개별 계산과 추천 계산의 산식 경로가 갈라지면 안 된다.

## 대상 범위

포함:

- 체육, 스포츠, 운동, 레저, 골프, 건강관리, 재활, 트레이닝, 경호/경찰 계열
- 일반 실기, 실기우수자
- 농어촌, 지역균형/지역인재, 기회균형, 기초생활 등 조건 전형
- 체대 계열 학생부교과/비실기 전형은 요청 조건에 따라 포함

제외:

- 비체대 일반학과
- 체육특기자, 경기실적, 선수전형
- 태권도/무도 단독 특기 선발
- 비체대 예술 실기
- 한밭대 빅데이터헬스케어융합학과 row 390/392

경호 계열은 체대입시 범위로 본다.

## 최종 검증 상태

- 코드 기반 차단 결함: 0건
- OCR/evidence 재판독 차단 결함: 0건
- 박시현 추천 파이프라인: PDF 원문 기준 정합 확정
- 호서대 9등급 이슈: 코드 수정 대상 아님. 런타임은 이미 `8.50~8.99=40`, `9.00=0` 구간표로 계산하며 테스트로 잠겨 있다.

## OCR 재판독 상태

텍스트 레이어가 사실상 없는 핵심 이미지 PDF:

- 나사렛대
- 배재대
- 동명대

이 3개교는 OCR 텍스트만 보고 판정하지 않는다. PDF 이미지 판독 결과를 우선한다.

텍스트 레이어는 있으나 evidence 정리가 필요한 학교:

- 경북대: evidence를 등급표 근거로 정리 권장
- 창원대: evidence를 예체능전형 등급표 근거로 정리 권장
- 공주대: `record_full_score=301.5`가 교과900+출결100+진로5의 30% 구조임을 주석화
- 울산대: grade table 320점과 학생부 400점 구조(진로40+출결40)를 주석화
- 호서대: 평균등급 구간표를 정수 9등급 표처럼 단순화하지 말 것

## 주요 잠금 판정

| 항목 | 최종 판정 |
|---|---|
| 나사렛대 row 106/107/108 | 확정일치 |
| 배재대 row 194/195/196/197 | 확정일치 |
| 동명대 row 159 | 확정일치 |
| 성결대 row 248/249 | 확정일치 |
| 공주대 row 99 | 확정일치 |
| 울산대 row 298/303 | 계산 정합, 스케일 주석만 필요 |
| 경북대 row 26/28 | 확정일치, evidence 정리만 필요 |
| 창원대 row 337 | 확정일치, 특기자 출결표를 예체능전형에 섞지 말 것 |
| 호서대 row 397/416 | 런타임 정합, DB/evidence 표기 주의 |
| 한밭대 row 390/392 | 대상 제외 |

## 외부 검증자에게 줄 기준

클로드나 다른 모델에게 재검증을 시킬 때는 아래 파일을 기준으로 준다.

- `docs/susi27-ocr-reread-claude-prompt-20260620.md`
- `docs/susi27-ocr-reread-report-20260620.md`
- `docs/susi27-ocr-reread-codex-report-20260620.md`
- `docs/susi27-final-code-aware-audit-report-20260620.md`

외부 Linux 환경에서는 reference pack을 clone한 뒤 DB 경로를 명시한다.

```bash
git clone https://github.com/etlab8320/miho-ai.git
git clone https://github.com/etlab8320/korea-susi27-athletic-reference.git
cd miho-ai
export MIHO_SUSI27_STAGING_DB="$(pwd)/../korea-susi27-athletic-reference/runtime/susi27_pipeline/susi27_staging.sqlite3"
```

## 검증 명령

미호 플러그인 추천 경로:

```bash
cd /Users/etlab/projects/miho-ai
./scripts/run_tests.sh tests/plugins/test_susi_ops*.py -- --tb=short
```

공식 산식 런타임:

```bash
cd /Users/etlab/.miho/discord/guilds/1507988396235296778/channels/10___1508422955460198420/threads/thread__1513557600497565696/work/susi27_pipeline
pytest -q test_susi27_formula_*.py --tb=short
```

호서대 9등급 구간 잠금:

```bash
cd /Users/etlab/.miho/discord/guilds/1507988396235296778/channels/10___1508422955460198420/threads/thread__1513557600497565696/work/susi27_pipeline
python3 test_susi27_formula_hoseo.py
```

## 현재 남은 일

계산 차단 결함은 없다. 남은 일은 운영 품질 정리다.

1. 경북대/창원대 evidence 문구를 원문 등급표 중심으로 교체
2. 공주대/울산대 스케일 주석 보강
3. 한밭대 대상 제외 플래그 문구 유지
4. 배재대 가산점 반영 여부를 evidence에 명시
5. 새 반박이 들어오면 PDF 이미지와 런타임 코드 양쪽을 다시 열어 판정

## 완료 정의

미호AI가 수시 추천 또는 개별 계산을 할 때 아래를 만족하면 완료로 본다.

- 학생부 환산점수는 공식 PDF 산식 런타임에서 나온다.
- 전년도 최종합격자 총점은 비교값으로만 쓰인다.
- 조건 전형은 사용자가 요청한 경우에만 추천 결과에 의미 있게 포함한다.
- 특기자/경기실적/비체대 학과는 기본 추천에서 제외된다.
- OCR이 낮은 학교는 텍스트 추출본이 아니라 PDF 이미지 판독 근거를 따른다.
