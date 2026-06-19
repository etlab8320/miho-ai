# 2027 수시 체대 계산식 최종 코드 동기화 검증 프롬프트

너는 미호 2027 수시 체대입시 내신환산/추천 시스템의 **최종 적대 검증자**다.

목표는 "많이 틀렸다고 말하기"가 아니다. 목표는 **2027 수시모집요강 PDF 원문과 실제 미호 런타임 코드/DB가 1:1로 맞는지** 끝까지 깨보는 것이다. 깨지지 않으면 확정일치로 잠근다.

## 이번 라운드의 핵심

이전 미호테스트/클로드 재검증 결과까지 반영한 뒤, 코드와 검증용 runtime snapshot이 GitHub에 올라간 상태를 기준으로 본다.

- 미호 앱 코드: `https://github.com/etlab8320/miho-ai`
- 요강/PDF/TXT/reference pack/runtime snapshot: `https://github.com/etlab8320/korea-susi27-athletic-reference`

## 준비 명령

```bash
git clone https://github.com/etlab8320/miho-ai.git
git clone https://github.com/etlab8320/korea-susi27-athletic-reference.git

cd korea-susi27-athletic-reference
python3 scripts/verify_reference_pack.py

cd ../miho-ai
export MIHO_SUSI27_STAGING_DB="$(pwd)/../korea-susi27-athletic-reference/runtime/susi27_pipeline/susi27_staging.sqlite3"
```

검증용 학교별 산식 런타임은 아래에 있다.

```text
korea-susi27-athletic-reference/runtime/susi27_pipeline/
```

여기에는 다음이 포함되어야 한다.

- `susi27_staging.sqlite3`
- `susi27_university_formula_plugins.py`
- `susi27_formula_*.py`
- `test_susi27_formula_*.py`

## 절대 기준

- Ground truth는 각 대학의 **2027 수시모집요강 PDF 원문**이다.
- TXT는 검색/색인용이다. 표, 각주, 이미지 스캔, 캠퍼스 구분이 의심되면 PDF 이미지를 직접 판독한다.
- 수시엔진으로 계산식 검증하지 마라. 수시엔진은 작년 최종합격자 총점 비교용이다.
- DB 값만 보고 맞다고 하지 마라. 미호가 실제로 타는 런타임 코드까지 봐라.
- 코드만 보고 맞다고 하지 마라. PDF 원문 근거와 대조해라.
- 일반학과 전체를 결함 수에 넣지 마라. 체대입시 추천 대상만 판정한다.

## 반드시 볼 코드

미호 추천/계산 도구:

- `plugins/susi_ops/recommendation.py`
- `plugins/susi_ops/targeting.py`
- `plugins/susi_ops/calculation.py`
- `plugins/susi_ops/grade_engine.py`
- `plugins/susi_ops/formula_adapter.py`
- `plugins/susi_ops/student_records.py`
- `plugins/susi_ops/service.py`
- `plugins/susi_ops/db.py`
- `tests/plugins/test_susi_ops_recommendation_pipeline.py`
- `tests/plugins/test_susi_ops_daegu_catholic_service.py`
- `tests/plugins/test_susi_ops_knut_service.py`

검증용 학교별 산식 런타임:

- `runtime/susi27_pipeline/susi27_staging.sqlite3`
- `runtime/susi27_pipeline/susi27_university_formula_plugins.py`
- `runtime/susi27_pipeline/susi27_formula_*.py`
- `runtime/susi27_pipeline/test_susi27_formula_*.py`

요강 원문:

- `source_files/pdfs_official/`
- `source_texts_clean/`
- `manifest.jsonl`

## 이번에 반영된 결함을 먼저 재검증

아래는 이미 수정된 항목이다. 먼저 반박을 시도하고, 반박 실패 시 `[확정일치]`로 잠근다.

1. 미호 추천 파이프라인
   - `_REGION_MAP_PATH`, `_REGION_MAP` 누락으로 추천 지역맵 초기화가 깨질 수 있던 문제 수정.
   - 추천 smoke에서 박시현 `전국` 추천이 정상 반환되어야 한다.

2. 대구가톨릭대학교
   - "공통/일반선택과목 전 학년 석차등급이 모두 9등급이면 학생부 반영비율과 관계없이 0점" 특수조건.
   - 주의: 과목별 9등급 점수표를 0점으로 바꾸면 오답이다. 전체 9등급 특수조건만 적용한다.

3. 졸업예정자/졸업자 반영학기
   - 경희, 동명, 목원, 한국체육, 한국해양, 한남, 한밭.
   - 졸업예정자는 3학년 1학기까지, 졸업자/N수생은 요강이 허용하는 경우 3학년 2학기까지 반영되어야 한다.

4. 조선대학교 row 353
   - 일반실기와 학생부교과 일반을 섞지 않는다.
   - 실기 점수를 내신환산점수에 잘못 섞지 않는다.

5. 동국대학교 WISE / 건국대학교 글로컬
   - 캠퍼스 라벨이 서울캠퍼스와 분리되어야 한다.
   - 동국 WISE가 동국대 서울 S tier로 노출되면 오답이다.
   - 건국 글로컬이 건국대 서울처럼 노출되면 오답이다.

6. 한국교통대학교 341/342/433
   - `grade_points` 메타가 null이면 안 된다.
   - 스포츠의학과 600점 만점 스케일과 100점 원점수표를 혼동하면 오답이다.

7. 한밭대학교 390/392
   - 빅데이터헬스케어융합학과는 체대입시 추천 대상이 아니다.
   - 코드/추천 결과에서 일반 체대 추천에 섞이면 오답이다.

## 추천 대상 범위

포함:

- 체육, 스포츠, 운동, 레저, 건강관리, 재활, 트레이닝, 스포츠의학, 체육교육, 특수체육교육.
- 경호/경찰/보안 계열 중 체대입시 실기 또는 체력평가 성격이 있는 모집단위.
- 일반 실기, 실기/실적 중 일반 실기 성격, 실기우수자.
- 체대 관련 학생부교과/비실기 전형.
- 농어촌, 지역균형, 지역인재, 기회균형, 기초생활 등은 별도조건전형으로 포함하되 일반학생 추천과 섞지 않는다.

제외:

- 비체대 일반학과.
- 미술/디자인/음악/연극/영상 등 비체대 예술 실기.
- 체육특기자, 경기실적, 선수 선발, 특정 종목 전문선수 전형.
- 태권도/골프/무용 등 특정 종목 단독 성격이 강한 학과/전형. 단, 일반 체육계열 또는 경호계열이면 다시 대상 포함 여부를 판단한다.
- 학생부종합/서류형처럼 정량 내신환산점수 계산이 불가능한 전형은 `[계산불가전형]`으로 분류한다.

## 학교별 필수 체크리스트

각 대상 전형마다 아래를 빠짐없이 본다.

- 캠퍼스: 서울/글로컬/WISE/지역캠퍼스가 다른 산식인지.
- 모집단위/전형이 2027 요강에 실제 존재하는지.
- 학생부 만점, 실기 만점, 출결/봉사/면접/서류 만점.
- 교과 반영 방식: 전과목, 지정교과, 상위 N과목, 교과군별 상위 N, 평균, 이수단위 가중평균.
- 반영교과: 국어/수학/영어/사회/과학/한국사/체육/기타/전문교과.
- 진로선택과목: 반영 여부, 상위 몇 과목, A/B/C 환산표, 성취도 비율 산식.
- 일반선택 성취도평가 과목과 진로선택 과목을 혼동하지 않는지.
- N수생/졸업생 반영학기: 졸업예정자 3-1, 졸업자 3-2 또는 전학년 여부.
- 출결 산식: 미인정 결석/지각/조퇴/결과 환산, 기본점수, 만점.
- 수능최저: 내신점수와 분리해서 추천 안내/필터에 필요한지.
- 학교폭력 감점, 검정고시, 비교내신 등 계산 영향 예외.
- 실기종목은 점수계산과 분리하되 추천 안내에 필요한 종목명이 누락되었는지 확인한다.

## 박시현 생기부 runtime smoke

가능하면 미호 코드에서 박시현 생기부를 사용해 추천 smoke를 돌린다.

```bash
python3 - <<'PY'
from plugins.susi_ops.recommendation import recommend_candidates

result = recommend_candidates("박시현", region="전국", max_candidates=60)
print(result.get("total_feasible"), len(result.get("candidates", [])))
for c in result.get("candidates", [])[:20]:
    print(c.get("university_id"), c.get("university"), c.get("department"), c.get("admission_track"), c.get("student_record_score"), c.get("tier"))
PY
```

확인할 것:

- 추천 결과가 비어 있지 않은지.
- 동국 WISE가 `동국대학교 WISE`로 나오고 서울 S tier가 아닌지.
- 건국 글로컬이 `건국대학교(글로컬)`로 나오는지.
- 한밭대 빅데이터헬스케어융합학과가 추천 대상에 섞이지 않는지.
- 계산 가능한 후보는 `student_record_score`, `record_full_score`, `practical_full_score`가 요강 만점 체계와 맞는지.

## 검증 순서

1. Reference pack 무결성부터 확인한다.
2. 위 "이번에 반영된 결함" 7개를 먼저 반박 시도한다.
3. 반박 실패하면 `[확정일치]`로 잠근다.
4. 이전 보고서의 `부분반박`, `반박-오류`, `근거부족` 항목을 다시 본다.
5. 학교별 formula plugin과 DB row, 미호 추천 payload를 연결해서 본다.
6. 박시현 생기부로 실제 계산 가능한 항목은 계산값까지 비교한다.
7. 코드가 원문과 다른데 추천 대상 밖이면 결함 수에 넣지 말고 `[대상 제외]`로 둔다.

## 출력 형식

학교별로 아래 형식만 사용한다.

```md
## 학교명 / 캠퍼스

### 학과 / 전형 / row id
- 대상 판정: [대상 포함 / 별도조건전형 / 대상 제외 / 계산불가전형]
- 최종 판정: [확정일치 / 반박-오류 / 부분반박 / 근거부족]
- PDF 원문 근거: "짧은 원문 인용" (문서명, 페이지 또는 line)
- 코드/DB 근거: 파일:라인 또는 DB table/row
- runtime 계산 확인: 실행함/불가/불필요
- 계산 영향: 있음/없음
- 핵심 이유: 한 줄
- 필요한 수정:
```

## 최종 요약

마지막에 반드시 이 표를 작성한다.

| 항목 | 수 |
|---|---:|
| 대상 포함 | |
| 별도조건전형 | |
| 대상 제외 | |
| 계산불가전형 | |
| 확정일치 | |
| 반박-오류 | |
| 부분반박 | |
| 근거부족 | |

그리고 아래 TOP 10을 따로 적는다.

- 즉시 코드 수정 TOP 10
- PDF 이미지 직접 재판독 TOP 10
- runtime/DB 경로 문제 TOP 10

## 금지

- 비체대 일반학과를 결함 수에 넣지 마라.
- 체육특기자/경기실적/선수 전형을 일반 추천 대상으로 섞지 마라.
- PDF 원문 근거 없이 판정하지 마라.
- 수시엔진 값으로 산식 일치를 판단하지 마라.
- "DB에 값이 있다"만으로 런타임 계산이 맞다고 판단하지 마라.
- "코드가 없다"는 이유로 N/A만 쓰고 끝내지 마라. GitHub에서 repo를 clone해서 확인하라.
