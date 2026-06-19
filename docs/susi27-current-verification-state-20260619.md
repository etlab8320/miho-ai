# 2027 수시 체대입시 산식 검증 상태 - 2026-06-19

## 목표 범위

- 추천/계산 대상: 체육, 스포츠, 운동, 레저, 골프, 건강관리, 재활, 트레이닝, 경호/경찰 계열.
- 포함: 일반 실기, 실기우수자, 체대 교과/비실기 전형, 농어촌/기회균형/지역균형/기초생활 등 요청 조건 전형.
- 기본 제외: 태권도/무도 단독 학과, 특기자/경기실적/종목별 선수 선발, 비체대 예술 실기(디자인/미술/연극/음악/영상 등).
- 경호/경찰 계열은 체대입시 범위로 보며, `무도경호학과`처럼 무도 단어가 섞여도 경호 계열이면 포함한다.

## 오늘 확정 수정

- 용인대학교:
  - 공식 요강의 학생부 반영방법은 예체능 계열 9과목(학년별 3과목), 사범계열 12과목(학년별 4과목)이다.
  - 특수체육교육과는 사범계열이므로 `YIU_2027_TEACHER_TOP4_PER_GRADE_DISTINCT_COURSE_RECORD30_FITNESS70`이 맞다.
  - DB row 283, 284의 `formula_key`, `top_n`, `per_grade_n`을 특수체육교육과 기준으로 수정했다.
  - DB 백업: `susi27_staging.sqlite3.codex_backup_before_yongin_teacher_formula_meta_20260619T230500`

- 추천 필터:
  - `plugins/susi_ops/targeting.py`로 추천 대상 판정 로직을 분리했다.
  - 경호/경찰 계열 포함, 비체대 예술 실기 제외, 공식요강 부재/계산금지/정성평가 row 제외를 명시했다.
  - `plugins/susi_ops/recommendation.py`는 새 필터를 사용하도록 연결했다.

- 비실기/교과 체대 row 메타:
  - 건양대 스포츠의학전공 농어촌/일반학생 row 11, 12의 `formula_key`를 `KONYANG_2027_SPORTS_MEDICINE_RECORD100`으로 동기화했다.
  - 경남대 스포츠재활 일반 row 17의 `formula_key`를 `KYUNGNAM_2027_OFFICIAL_RECORD_INTERVIEW_PRACTICAL`로 동기화했다.
  - 신라대 체육학부 일반고교과 row 278의 `formula_key`를 `SILLA_2027_RECORD1000`으로 동기화하고 수능최저 없음 메타를 정규화했다.
  - DB 백업: `susi27_staging.sqlite3.codex_backup_before_record_only_formula_key_sync_20260619T233000`
  - DB 백업: `susi27_staging.sqlite3.codex_backup_before_record_only_formula_key_sync_r2_20260619T234000`

## 현재 감사 결과

- 외부 산식 DB 전체 row: 413.
- 추천 후보 감사 기준:
  - 전년도 결과가 있고 verified 계열인 row: 399.
  - 공식요강 부재/계산금지/정성평가로 차단한 row: 103.
  - 추천 허용 범위 row: 179.
  - 특정 종목/선수 선발 제외 row: 4.
  - 실제 후보 row: 175.
  - 실기 후보 row: 124.
  - 비실기/교과 후보 row: 51.
  - 전체 후보 중 `formula_key` 누락: 0.
  - 실기 후보 중 `formula_key` 누락: 0.

## 검증 명령

```bash
cd /Users/etlab/.miho/discord/guilds/1507988396235296778/channels/10___1508422955460198420/threads/thread__1513557600497565696/work/susi27_pipeline
pytest -q test_susi27_formula_yongin.py --tb=short
pytest -q test_susi27_formula_konyang.py test_susi27_formula_kyungnam.py test_susi27_formula_silla.py --tb=short
pytest -q test_susi27_formula_*.py --tb=short
```

결과:

- `test_susi27_formula_yongin.py`: 10 passed.
- `test_susi27_formula_konyang.py test_susi27_formula_kyungnam.py test_susi27_formula_silla.py`: 31 passed.
- `test_susi27_formula_*.py`: 673 passed.

```bash
cd /Users/etlab/projects/miho-ai
./scripts/run_tests.sh tests/plugins/test_susi_ops_recommendation_pipeline.py -- --tb=short
./scripts/run_tests.sh tests/plugins/test_susi_ops_*.py -- --tb=short
```

결과:

- `test_susi_ops_recommendation_pipeline.py`: 12 passed.
- `tests/plugins/test_susi_ops_*.py`: 91 files, 322 tests passed, 0 failed.

## 커밋 범위 메모

커밋 포함 후보:

- `plugins/susi_ops/targeting.py`
- `plugins/susi_ops/recommendation.py`
- `tests/plugins/test_susi_ops_recommendation_pipeline.py`
- 외부 파이프라인 DB `susi27_staging.sqlite3`의 row 11/12/17/278/283/284 메타 수정
- 외부 파이프라인 `test_susi27_formula_yongin.py`
- 외부 파이프라인 `test_susi27_formula_konyang.py`
- 외부 파이프라인 `test_susi27_formula_kyungnam.py`
- 외부 파이프라인 `test_susi27_formula_silla.py`
- 이 문서

주의:

- `/Users/etlab/projects/miho-ai/susi27_staging.sqlite3`는 repo-local 빈/오염 DB라 커밋 대상이 아니다.
- 실제 수시 DB는 `/Users/etlab/.miho/discord/guilds/1507988396235296778/channels/10___1508422955460198420/threads/thread__1513557600497565696/work/susi27_pipeline/susi27_staging.sqlite3`이다.
- repo에는 이전부터 관련 없는 수정/신규 파일이 많다. 커밋은 위 범위만 선별해야 한다.
