# Academy Result Reviewer Spec

## Problem

학종 PDF, 실기 추천 PDF, 생기부 저장, 수시 추천은 결과가 그럴듯해 보여도
도구 우회, 산식 오류, 근거 누락, PDF 레이아웃 문제를 놓치면 운영 사고가 된다.

## Scope

In:
- 전용 도구 우회 방지: 일반 코드/파일 도구로 학종·실기 PDF나 수시 산식을 직접 만들지 못하게 한다.
- 결과 후검증: 고위험 도구 성공 결과를 사용자 전달 전 다시 검수한다.
- 이중 검증: 재현 가능한 오류는 코드 하드게이트가 막고, 내용/의도/레이아웃은 LLM reviewer가 본다.
- 실패 시 같은 전용 도구 재호출 지시를 반환한다.

Out:
- 자동 무한 재시도 루프.
- 사용자의 명시 확인 없이 생기부 `needs_review`를 확정 처리하는 흐름.
- 기존 `decision_twin` 라우팅 구조 교체.

## Acceptance Criteria

- `execute_code`/`terminal` 등이 학종·실기 PDF를 직접 만들려 하면 차단한다.
- `academy_hakjong_report_package` 성공 결과는 canonical manifest와 reviewer LLM 통과가 필요하다.
- `academy_practical_reco_package` 성공 결과는 `susi27_recommend_candidates` 근거와 reviewer LLM 통과가 필요하다.
- `susi27_recommend_candidates`는 만점 합산이 전년도 최종합보다 낮은 후보를 통과시키지 않는다.
- 생기부 `needs_review`는 차단이 아니라 사람 검수 필요 상태로 표시하고 확정 표현을 금지한다.

## Future Route Reviewer

라우팅 reviewer는 기존 `decision_twin` 뒤에 붙이는 2차 게이트가 적합하다. 모든 요청마다
무거운 subagent를 돌리지 않고, 생기부·수시·학종·실기·쓰기/삭제처럼 고위험이거나
confidence가 낮은 턴만 빠른 LLM reviewer가 재판정한다.

권장 흐름:

1. `decision_twin`이 1차 route와 required_tool을 결정한다.
2. 고위험/저신뢰 턴만 `academy_route_reviewer`가 의도와 필수 인자를 검수한다.
3. 통과하면 기존 route로 진행한다.
4. 실패하면 질문, route rewrite, 또는 required_tool 강제 지시를 반환한다.

## Test Plan

- reviewer unit tests: 차단, 통과, LLM 실패, 생기부 needs_review.
- academy plugin registry tests: `pre_tool_call`, `transform_tool_result`, auxiliary task 등록.
- PDF/report tests: 학종·실기 결과 계약 유지.
- routing tests: 기존 `decision_twin` 계약 유지.
