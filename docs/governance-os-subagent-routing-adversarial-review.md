# Governance OS Subagent Routing — Adversarial Review Summary

작성일: 2026-06-25
대상: Miho Governance OS / auxiliary subagent routing / final delivery gate

## 최종 결론

전부 고쳤다고 보기는 어렵다. 하지만 핵심 구조는 확실히 좋아졌다.

현재 판정은 다음과 같다.

```text
서브에이전트 dispatcher 실제 호출: 있음
서브에이전트 reviewer 실제 호출: 있음
Final Delivery Gate: 이전보다 더 강하게 차단
Readiness: 100점
Focused Governance tests: 통과
신규 에이전트/도구: Pixel Document Evidence, Sports Performance coach/reviewer 추가 확인
남은 리스크: gate/guard 오탐, transform hook ordering, promotion judge data-plane
```

한 줄 판정:

> 이제 Governance OS는 실제 런타임 OS처럼 굴러가기 시작했다. 다만 아직 완전한 자율 판단 OS라고 부르기엔 문지기가 가끔 아군도 막는다.

## 2026-06-25 ET Dev OS 후속 적용 결과

이 리뷰의 주요 지적 중 일부는 현재 소스와 테스트에서 해결 확인됐다.

```text
dispatcher 후보 밖 playbook accept: 해결 확인
auxiliary reviewer always 정책: high-risk playbook 기반으로 조정
Final Delivery Gate 진행/안전 문구: 보강, 단 점수/완료 주장과 섞이면 block 유지
저위험 Discord 첨부 전달: deterministic reviewer pass면 auxiliary provider 장애와 독립적으로 통과
delegate heartbeat 실패: 현재 재검증 통과
```

후속 검증:

```text
scripts/run_tests.sh $(rg --files tests/plugins | rg 'governance_os') tests/tools/test_delegate.py
=> 252 passed

uv run ruff check plugins/governance_os tests/plugins/test_governance_os_delivery_gate.py tests/plugins/test_governance_os_review_retry.py tests/plugins/test_governance_os_council.py
=> All checks passed

uv run ty check plugins/governance_os/review.py plugins/governance_os/result_transform.py plugins/governance_os/delivery_gate.py plugins/governance_os/council.py tests/plugins/test_governance_os_delivery_gate.py tests/plugins/test_governance_os_review_retry.py tests/plugins/test_governance_os_council.py
=> All checks passed
```

## 검증 결과

### 이번 추가 검증 범위

이번 업데이트에서 새로 확인한 축은 세 가지다.

```text
1. Governance OS subagent routing / final delivery gate
2. Pixel Document Evidence reviewer agent / core tool
3. Sports Performance coach/reviewer agent / PE-brain evidence / video analysis contract
```

### 통과한 검증

```bash
python -m pytest tests/plugins/test_governance_os*.py   tests/tools/test_governance_os_tool.py   tests/tools/test_media_delivery_contract_tool.py   tests/e2e/test_discord_governance_delivery.py   tests/e2e/test_governance_os_subagent_routing_smoke.py   tests/test_transform_llm_output_hook.py -q
```

결과:

```text
145 passed, 1 warning
```

Readiness:

```text
ready=True
quality_score=100
failures=()
aux_dispatch=True
aux_review=True
final_delivery=True
```

Static check:

```text
git diff --check clean
obvious added-line secret / shell injection / eval / pickle / SQL-format scan: no hit
```

### 이전 실패 검증 업데이트

이전 묶음 검증에서는 delegate heartbeat 1개 실패가 있었다.

```text
1 failed, 209 passed
```

실패 테스트:

```text
tests/tools/test_delegate.py::TestDelegateHeartbeat::test_heartbeat_does_not_trip_idle_stale_while_inside_tool
```

실패 내용 요약:

```text
expected heartbeat touches >= 6
got 3 touches over 0.4s at 0.05s interval
```

현재 재검증 결과:

```text
scripts/run_tests.sh tests/tools/test_delegate.py
=> 135 passed
```

따라서 이 항목은 현재 Governance OS 후속 적용 범위에서는 stale failure로 본다.

## 좋아진 점

### 1. Dispatcher subagent는 이제 실제 호출된다

이전에는 auxiliary task 등록만 있고 실제 판단 호출이 없었다. 이번에는 실제 호출 경로가 있다.

```python
async_call_llm(task="miho_governance_dispatcher", ...)
```

동작 구조:

```text
명확한 요청 -> deterministic fast path
애매한 요청 -> miho_governance_dispatcher
dispatcher 실패 -> deterministic_fallback
```

이전의 “control-plane만 있음” 지적은 이제 대부분 해소됐다.

### 2. Reviewer subagent도 실제 호출된다

의미 검증이 필요한 결과에서는 reviewer auxiliary task를 호출한다.

```python
call_llm(task="miho_governance_reviewer", ...)
```

그리고 reviewer provider가 죽거나 JSON이 깨지면 fail-closed로 막는다.

```text
auxiliary_reviewer_unavailable -> fail
```

사용자에게 내부 provider error, task key, traceback을 노출하지 않는 점도 좋다.

### 3. Final Delivery Gate가 더 강해졌다

이전 구조는 marker 기반에 가까웠다.

```text
완료 / 첨부 / 전달 / 계산 / 저장 / PDF / 점수 / 리포트 같은 표현 감지
```

현재 구조는 더 강하다.

```text
governed playbook 감지
-> review pass evidence 있으면 allow
-> safe non-delivery response면 allow
-> 그 외 block
```

즉 확정성 있는 최종 답변이 marker를 피해 빠져나가는 문제는 줄었다.

### 4. Current turn evidence를 다시 review gate로 검증한다

`conversation_history`에서 현재 turn의 tool result를 찾아 단순히 reviewer dict만 믿지 않고 다시 검증한다.

```python
evaluate_review_gate(..., auxiliary_review_policy="always")
```

즉 현재 turn evidence 검증은 이전보다 단단해졌다.

### 5. Manifest 가시성도 개선됐다

`plugin.yaml`에 auxiliary task 선언이 들어갔다.

```yaml
provides_auxiliary_tasks:
  - miho_governance_dispatcher
  - miho_governance_reviewer
  - miho_governance_promotion_judge
```

운영/doctor/readiness 관점에서 더 낫다.

## 남은 적대적 리스크

## Critical

현재 기준에서 즉시 배포를 막을 Governance OS 본체 Critical은 확인하지 못했다.

후속 검증 기준으로 Governance OS 관련 focused suite와 delegate suite는 clean이다.

## Resolved 1 — Dispatcher subagent 결과 candidate 제한

현재 소스는 auxiliary dispatcher 결과를 scored candidates 안의 playbook으로 제한한다.

```python
candidate_keys = {candidate.playbook_key for candidate in candidates}
if candidate_keys and playbook_key not in candidate_keys:
    return None
```

그리고 `tests/plugins/test_governance_os_dispatcher.py`에 후보 밖 결과를 거부하는 테스트가 있다. 이 문서의 원래 Major 1은 현재 기준 stale이다.

## Major 2 — Final Delivery Gate는 안전해졌지만 오탐 가능성이 커졌다

현재는 governed playbook으로 잡히면 review pass evidence가 없는 대부분의 최종성 응답을 막는다.

좋은 점:

```text
누락 감소
```

나쁜 점:

```text
단순 설명 / 진행 상태 / 검토 의견까지 막을 수 있음
```

후속 적용 전에는 safe non-delivery marker가 제한적이었다.

기존 safe marker 예:

```text
필요합니다
확인이 필요
원본 대조
전용 도구
후검증
다시 실행
수 없습니다
못했습니다
진행할 수
```

보강한 상태 보고 후보:

```text
확인 중입니다.
작업을 시작하겠습니다.
계산을 준비하겠습니다.
잠시만 기다려 주세요.
```

후속 적용에서 이 상태 안내 문구는 보강했다. 다만 `확인 중입니다. 서연이 수시 환산점수는 947.3점입니다.`처럼 진행 문구와 실제 점수/완료 주장이 섞이면 여전히 block한다. 남은 리스크는 self-review/dev-review 문맥이나 긴 설명문이 governed domain 용어를 많이 포함할 때의 오탐이다.

## Resolved 2 — auxiliary reviewer always 정책

이전에는 current turn tool result 복원, tool-result transform, council path가 모두 다음 정책을 썼다.

```python
auxiliary_review_policy="always"
```

좋은 점:

```text
semantic 검증 강화
```

나쁜 점:

```text
provider 장애 시 이미 tool-level reviewer pass가 있어도 final delivery가 막힐 수 있음
응답 직전 latency 증가
tool result가 여러 개면 비용/시간 증가
```

후속 적용에서 공용 정책으로 변경했다.

```text
high-risk: academy_hakjong_report, academy_practical_recommendation, susi_score_calculation, life_record_ingest, research_brief -> always
low-risk/default: semantic flag가 있을 때만 auxiliary reviewer 호출
```

검증 추가:

```text
저위험 Discord 첨부 전달은 attachment_delivery_review pass가 있으면 auxiliary provider offline이어도 통과
고위험 수시 점수 계산은 semantic flag 없이도 miho_governance_reviewer 호출 유지
research_brief는 source/date 민감도가 있어 auxiliary reviewer 호출 유지
```

## Major 4 — Governance guard false-positive가 아직 실제로 발생한다

리뷰 과정에서 검증용 terminal/search 명령이 Governance guard에 막혔다.

원인:

```text
리뷰/테스트 명령 안에 governed domain 표현이 들어가면 산출물 생성으로 오인
```

리스크:

```text
Governance OS가 자기 자신을 리뷰하거나 문서화하는 dev workflow를 막을 수 있음
```

권장 수정:

```text
repo 내부 docs/tests/plugins/governance_os 대상 작업은 dev review context로 우선 분류
read/search/test 계열 명령은 artifact bypass로 오인하지 않기
forbidden guard는 생성/전달 intent가 명확할 때만 block
```

## Resolved 3 — Delegate heartbeat 테스트 실패

이전 검증에서는 `tests/tools/test_delegate.py` heartbeat 테스트가 실패했다.

실패 메시지:

```text
Heartbeat stopped too early while child was inside a tool;
got 4 touches over 0.4s at 0.05s interval
```

이건 Governance OS 본체와 직접 관련은 약하지만, 변경 묶음 안에 있으므로 최종 clean 상태는 아니다.

현재 재검증:

```text
tests/tools/test_delegate.py: 135 passed
```

따라서 현재 적용 상태에서는 실패 항목으로 유지하지 않는다.

## Medium 1 — Promotion judge는 아직 실전 data-plane이 약하다

등록은 되어 있다.

```text
miho_governance_promotion_judge
```

하지만 실제 LLM judge로 promotion 판단을 수행하는 runtime path는 dispatcher/reviewer보다 약하다. 현재 promotion 쪽은 deterministic recurrence / tests / snapshot / rollback validation 중심이다.

이건 안전상 나쁜 것은 아니다. 다만 “3개 subagent 모두 실전 판단 중”이라고 말하면 과장이다.

정확한 표현:

```text
dispatcher/reviewer data-plane은 연결됨
promotion judge는 주로 control-plane / deterministic governance path
```

## Medium 2 — transform_llm_output hook은 first string wins 구조다

`agent/conversation_loop.py`에서 `transform_llm_output` hook 결과 중 첫 non-empty string이 final response를 대체한다.

리스크:

```text
여러 plugin이 같은 hook을 쓰면 순서 의존성이 생김
Governance OS가 최종 방화문이어야 한다면 priority/ordering 보장이 필요
```

## 현재 점수

```text
Subagent dispatcher data-plane: 80~85%
Subagent reviewer data-plane: 85~88%
Final Delivery Gate 안전성: 84~88%
Final Delivery Gate UX 안정성: 70~76%
Guard 오탐 방어: 55~60%
Readiness/tests: 94~96%
전체 판정: 91~94%
```

## 최종 판정

이번 수정은 확실히 전진했다.

특히 다음 세 가지는 좋아졌다.

```text
1. dispatcher/reviewer subagent 실제 호출 경로 있음
2. final delivery gate가 더 강한 default-block 방향으로 바뀜
3. current turn evidence를 auxiliary reviewer로 다시 검증함
```

하지만 아직 “전부 고쳤다”고 말하면 안 된다.

남은 핵심은 이 네 가지다.

```text
1. final gate/guard false-positive를 더 줄이기
2. transform_llm_output hook priority/ordering 보장
3. promotion judge를 실전 data-plane으로 연결할지 결정
4. self-review/dev-review context를 더 명확히 분리
```

최종 한 줄:

> Governance OS는 이제 실제 OS처럼 작동하기 시작했다. 다만 최종 문지기와 도구 경비가 아직 가끔 아군까지 막는다.
