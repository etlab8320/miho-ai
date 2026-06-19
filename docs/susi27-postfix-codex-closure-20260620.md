# SUSI27 Postfix Codex Closure - 2026-06-20

## 처리 결과

Claude 재검증 리포트의 남은 진짜 결함 3개를 Codex 로컬 코드/DB 기준으로 재검증하고 닫았다.

## 수정

### 1. 캠퍼스 라벨/tier

- `plugins/susi_ops/recommendation.py`
- 동국대 WISE row(147, 148, 149, 151, 152, 153, 154, 156)는 추천 결과 대학명을 `동국대학교 WISE`로 표시한다.
- 건국대 글로컬 row(9, 10)는 추천 결과 대학명을 `건국대학교(글로컬)`로 표시한다.
- 동국대 서울 row(155)는 기존 `동국대학교` S tier를 유지한다.
- WISE는 `동국대학교` S tier 규칙에 걸리지 않도록 분리했다.

### 2. 한국교통대 스포츠의학 grade_points

- DB: `susi27_staging.sqlite3`
- row 341, 342, 433 `score_logic_json.grade_points`에 600점 만점 스케일을 보강했다.
- 100점 원점수표는 `grade_conversion_points`에 유지했다.
- 백업: `susi27_staging.sqlite3.codex_backup_before_knut_grade_points_20260620T004830`

### 3. 한밭대 빅데이터헬스케어융합학과

- 코드상 이미 체대 추천 대상에서 제외되고 있었다.
- `빅데이터헬스케어융합학과`가 `_is_allowed_recommendation_target(...)=False`임을 테스트로 잠갔다.

## 검증

- `./scripts/run_tests.sh tests/plugins/test_susi_ops_recommendation_pipeline.py tests/plugins/test_susi_ops_knut_service.py tests/plugins/test_susi_ops_daegu_catholic_service.py -- --tb=short`
  - 21 passed
- `pytest -q test_susi27_formula_knut.py test_susi27_formula_daegu_catholic.py test_susi27_formula_dongmyeong.py test_susi27_formula_kyunghee.py test_susi27_formula_hanbat.py --tb=short`
  - 36 passed
- `./scripts/run_tests.sh tests/plugins/test_susi_ops*.py -- --tb=short`
  - 326 passed, 0 failed
- `python3 -m py_compile ...`
  - 통과

## 남은 리스크

- 수능최저 안내 플래그, 일부 OCR 재판독 항목은 이번 결함 3개와 별도 라운드다.
- frontend/API/CORS/auth/browser smoke는 이번 변경이 Python plugin 내부 추천 payload와 SQLite 산식 메타에 한정되어 별도 실행하지 않았다.
