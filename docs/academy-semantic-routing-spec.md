# Academy Semantic Routing Spec

## Problem
미호 학원 라우터는 판매 제품 기준에서 상용 LLM처럼 사용자의 문장을 이해해야 한다. 특정 문장, 학생명, 학원명, 날짜 표현을 코드에 외워서 맞히는 방식은 금지한다. 테스트는 정답지를 외우게 만드는 장치가 아니라, 라우터가 의미와 맥락을 일반화해서 판단하는지 확인하는 시험이어야 한다.

## Users And Jobs
- 원장/운영자는 자연어로 출석, 수업, 실기 기록, 월말테스트, 학생 카드, 이미지 요청을 말한다.
- 미호는 문장 전체의 목적, 시제, 직전 맥락, 로그인 계정, 도구 계약을 함께 보고 올바른 실행 경로를 고른다.
- 도메인이 불명확하면 억지로 학원 도구를 실행하지 않고 본문 LLM으로 넘긴다.

## Scope

### In
- 의미 기반 라우팅 기준.
- 시제와 날짜 범위 판단 기준.
- 테스트/벤치마크로 검증할 항목.
- 하드코딩 금지 규칙.

### Out
- 실제 라우터 코드 수정.
- DB 마이그레이션.
- 프론트엔드 UI 변경.
- 운영 배포.

## Acceptance Criteria
- 특정 한국어 키워드 포함 여부만으로 학원 의도를 결정하지 않는다.
- 특정 학생명, 학교명, 지점명, 학원 ID, 서버 주소, 테스트 문장을 라우팅 예외로 넣지 않는다.
- 새 라우팅 수정은 일반화된 의도, 도구 계약, 시간 해석, 신뢰도, fallback 규칙 중 하나로 설명 가능해야 한다.
- 테스트 실패를 고칠 때는 실패 문장 자체를 코드에 추가하지 않고, 같은 의미의 다른 표현도 통과하도록 고친다.
- 계정/학원 경계는 로그인 토큰과 현재 실행 컨텍스트로 검증하고, 기본 학원 ID로 보정하지 않는다.

## Domain Model
- Utterance: 사용자가 입력한 원문.
- Intent: 사용자가 실제로 원하는 업무 목적.
- Temporal Frame: 오늘/어제/이번 주/다음 달 같은 상대 시간과 과거/현재/미래 시제.
- Thread Context: 직전 학원업무 응답, 학생, 기간, pending request.
- Tool Contract: 실행 가능한 학원 도구와 허용 인자.
- Tenant Context: 로그인 계정이 속한 학원/지점 경계.

## Routing Standard
- 1차 판단은 LLM 라우터 또는 실제 semantic embedding 기반이어야 한다.
- fallback은 장애 대응용이어야 하며, 특정 문장을 외우는 방식이면 안 된다.
- 라우터는 다음 순서로 판단한다.
  1. 학원업무 도메인인지 판단한다.
  2. 사용자의 실제 목적을 intent로 정한다.
  3. 날짜와 시제를 ISO 날짜/범위로 해석한다.
  4. 직전 맥락을 이어받아야 하는 후속 질문인지 확인한다.
  5. 도구 계약에 맞는 도구와 인자만 만든다.
  6. confidence가 낮거나 계약에 맞지 않으면 본문 LLM으로 넘긴다.

## Forbidden Fixes
- `if "출석" in text`처럼 사용자 문장의 특정 한국어 문자열을 직접 검사해서 라우팅하는 코드.
- 테스트에 나온 문장을 그대로 예외 목록에 추가하는 코드.
- 강남/일산 같은 특정 지점명으로 라우팅을 보정하는 코드.
- 박서현/김보민 같은 특정 학생명을 기준으로 저장 또는 조회 경로를 바꾸는 코드.
- `academy_id = 2` 같은 기본 학원 폴백.
- 서버 주소, 토큰, 계정, 비밀번호 기본값을 코드에 박는 방식.

## Allowed Fixes
- LLM 라우터 system prompt의 일반 원칙 보강.
- 도구 계약의 설명과 허용 인자 정리.
- 시제/날짜 해석 모듈의 일반 규칙 보강.
- semantic embedding anchor의 의도 범주 개선.
- confidence threshold, negative anchor, abstain 조건 조정.
- 직전 대화 맥락 저장/전달 구조 개선.
- anti-hardcoding 테스트와 의미 일반화 벤치마크 추가.

## Test Plan
- Anti-hardcoding scan: 한국어 문자열 직접 매칭, 특정 학생/지점/학원 ID 예외, 서버 기본값을 검사한다.
- Semantic benchmark: 같은 의도를 50개 이상 다른 표현으로 바꿔 route/tool/args가 안정적인지 확인한다.
- Temporal benchmark: 어제/오늘/내일/지난달/다음 주/이미 체크된/예정된 표현을 분리한다.
- Context benchmark: "그 학생만", "이미지로", "아까 거 다시" 같은 후속 질문이 직전 맥락을 올바르게 잇는지 확인한다.
- Negative benchmark: 학원업무가 아닌 요청은 학원 도구로 끌고 가지 않는지 확인한다.
- Tenant smoke: 강남 계정과 일산 계정이 서로 다른 학원 데이터로 저장/조회되지 않는지 확인한다.
- Speed check: warm 상태에서 라우터 p95를 측정하고, timeout 시 사용자에게 내부 오류 표현 없이 안전하게 본문 LLM 경로로 넘긴다.

## Operating Loop
- Initial baseline: 제품화 전 최소 기준 테스트셋을 만들고, 그 기준을 통과할 때까지 라우터를 수정한다.
- Quality rule: 실패를 고칠 때마다 구현을 리뷰하고, anti-hardcoding 검사와 관련 라우팅 테스트를 다시 돌린다.
- Release gate: 기준 테스트, 테넌트 경계, 속도 확인이 통과하기 전에는 판매용 안정 상태로 보지 않는다.
- Runtime logging: 출시 후에는 실제 사용 로그에서 실패 유형, 오타/비문, 시제 혼동, 도구 선택 실패, 계정 경계 위험을 분류한다.
- Human review: 운영 로그는 자동 코드 수정 재료가 아니라 테스트 후보와 개선 후보로만 사용한다.
- Generalized fix: 승인된 개선은 특정 로그 문장 암기가 아니라 의미 규칙, 도구 계약, 시간 해석, 맥락 처리, confidence 조정으로 반영한다.
- Regression loop: 새 실패 유형을 테스트셋에 추가한 뒤 기존 기준 테스트와 함께 다시 돌린다.

## Implementation Tasks
- [ ] T1: 라우팅 벤치마크 데이터셋을 만든다.
  - Files: `tests/plugins/`
  - Tests: 의미/시제/맥락/negative case.
  - Acceptance: 같은 의도 표현 변형이 특정 문장 암기 없이 통과한다.
- [ ] T2: anti-hardcoding 검사 범위를 확장한다.
  - Files: `tests/plugins/test_academy_no_hardcoded_nlp.py`
  - Tests: 학생명, 지점명, 학원 ID, 서버 기본값 금지.
  - Acceptance: 예외 추가식 수정이 테스트에서 바로 잡힌다.
- [ ] T3: 라우터 실패 시 fallback 품질을 검증한다.
  - Files: `plugins/academy_ops/`, `tests/plugins/`
  - Tests: timeout/ambiguous/low confidence.
  - Acceptance: 사용자는 코딩 용어, CORS, 400/401, stack trace를 보지 않는다.
- [ ] T4: 테넌트 경계 smoke를 만든다.
  - Files: `tests/plugins/`
  - Tests: 로그인 계정과 요청 학원 경계 불일치.
  - Acceptance: 기본 학원 폴백 없이 현재 계정 경계만 사용한다.

## Risks
- 라우터를 너무 엄격하게 만들면 학원업무 요청을 놓칠 수 있다.
- 라우터를 너무 넓게 만들면 일반 대화가 학원 도구로 빨려 들어갈 수 있다.
- embedding provider 장애 시 비의미 fallback으로 떨어지면 품질이 낮아질 수 있다.
- 테스트 데이터가 특정 문장에만 치우치면 다시 문장 암기형 구현을 유도할 수 있다.

## Product Rule
미호 라우터의 목표는 "테스트 문장 맞히기"가 아니라 "상용 LLM처럼 문장을 이해하고, 필요한 도구를 빠르고 정확하게 고르는 것"이다. 라우팅 문제를 고칠 때마다 이 문서를 기준으로 하드코딩 여부를 먼저 확인한다.
