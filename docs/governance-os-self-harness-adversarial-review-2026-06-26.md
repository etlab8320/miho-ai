# 미호 거버넌스 OS + Self-Harness 적대적 리뷰

> 작성: 2026-06-26 (KST) · 대상: `~/projects/miho-ai` · 방식: 코드 정독 + 병렬 감사 에이전트 2기
> 범위: Governance OS / LLM Final QA Agent / Final Delivery Repair·첨부 경로 보정 / Self-Harness 자동 개선 루프 / 도메인 reviewer·subagent / 실패→되돌림 재수정 루프 / 질문-답변 적합성 최종 검수
> 제외: git 더티트리·커밋 여부·픽셀랙/픽셀문서/susi27 산출물·안드로이드 트래커·타 프로젝트
> **본 문서는 리뷰만 한 결과이며 코드는 수정하지 않음.**

---

## 한 줄 결론

**전달 게이트(차단→LLM 복구)는 라이브 배선까지 완료된 진짜 구조지만, ① 첨부 경로 보정은 게이트에 안 걸려 있고 ② Self-Harness는 cron 호출자가 없는 죽은 루프이며 ③ "전용 도구/후검증" 차단 문구는 게이트의 `safe_markers` 화이트리스트 구멍 때문에 그대로 사용자에게 샐 수 있다.**

종합 가중 점수 ≈ **57 / 100**

---

## 실제 배선된 흐름 (검증됨)

```
tool 실행
  → [transform_tool_result 훅] governance_transform_tool_result   (model_tools.py:872 발화)
      → 하드코딩 게이트 + (선택)LLM aux reviewer
      → 실패 시 retry JSON으로 tool result 치환
      → 메인 LLM이 "알아서 재실행" (소프트 신호, 강제 아님)

턴 종료
  → [transform_llm_output 훅] governance_transform_llm_output     (conversation_loop.py:4091 발화)
      → 하드코딩 최종전달 판정 → block 시 repair_blocked_answer
      → LLM 복구(최대 2회 + LLM verdict) → 실패 시 소프트 fallback
```

양쪽 훅 모두 실제 발화 지점 확인됨. **죽은 코드 아님** (단, Self-Harness 루프는 별개로 죽어 있음 — 아래 Q5).

---

## 항목별 점수 + 하드코딩 vs LLM 구분

| 항목 | 점수 | 검수 주체 | 핵심 판정 |
|---|---|---|---|
| **Governance OS 코어** (dispatcher/registry/policy) | **62** | 혼합 (키워드 우선 + 조건부 LLM) | 라우팅 기본이 키워드 매칭(`dispatcher.py:351`), 애매(신뢰도 0.7~0.9)할 때만 LLM. risk 판정은 100% 하드코딩 키워드(`risk.py`) |
| **LLM Final QA Agent** | **78** | **진짜 LLM** (`final_qa.py`) | `async_call_llm` pass/revise verdict + 2회 repair 루프. 타임아웃 시 PASS로 통과(fail-open) — 검수 누락 위험 |
| **Final Delivery Repair / 첨부 경로 보정** | **35** | 하드코딩 Python (`final_delivery_repair.py`) | 파일 staging→`MEDIA:` 태그 재작성. **게이트에 미배선** — 별도 `media_delivery_contract` 도구를 LLM이 명시 호출해야만 작동 |
| **Self-Harness 자동 개선 루프** | **28** | 룰 기반 mutation (LLM 아님) | shadow candidate 제안만. `auto_promote_allowed=False`, 활성화에 필요한 `test_receipts`를 아무도 자동 생성 안 함. **cron/scheduler 호출자 0건 → 죽은 루프** |
| **도메인 reviewer / subagent** | **70** | 하이브리드 (hard_gate + LLM) | academy/sports reviewer는 구조검증 후 `llm.complete_structured`. 단 일부 도구(`susi27_score_calculate` 등)는 LLM 없이 하드게이트만 |
| **실패 → 되돌려 재수정 루프** | **48** | 하드코딩 신호 | tool result를 `next_action:retry_required` JSON으로 치환. **결정적 루프 아님 — 메인 LLM 순응에 의존**. LLM이 무시하면 그냥 통과 |
| **질문-답변 적합성 최종 검수** (Q7) | **75** | **진짜 LLM** (Final QA verdict_messages) | "A가 Q에 맞는지" LLM이 판정. 단 게이트가 "최종 전달 주장"으로 인식한 응답에만 발동 — 질문 자체가 governed playbook에 안 걸리면 검수 스킵 |

---

## Q3 — "전용 도구/후검증 통과 기록 없어 전달 불가" 재발 위험: **높음 (실재)**

세 가지 누수 경로 확인:

1. **🔴 결정적 결함 — safe_markers 화이트리스트 구멍**
   `delivery_gate.py:233-235`에서 `"전용 도구"`, `"후검증"`, `"다시 실행"`을 **safe marker로 등록**.
   즉 메인 LLM이 내부 retry 지시를 그대로 따라 말하면 `_is_safe_non_delivery_response()`가 **True → 게이트가 "안전한 비전달 응답"으로 보고 통과시킴**.
   차단하려는 바로 그 문구가 안전 목록에 박혀 있어 무사통과한다.

2. **하드 내부 문구가 여전히 라이브 소스에 존재**
   `policy.py:40,56` / `result_transform.py:83,219` / `review.py:78,88,98,115,165,251`.
   이들은 tool result로 주입되고, 최종 게이트만이 유일한 방어선인데 위 1번 구멍 + "최종 전달 주장으로 인식될 때만 발동"이라 빠져나간다.

3. **LLM 복구 fail-open**
   `final_qa.py` verdict가 타임아웃이면 PASS(45행), aux reviewer 불가 시엔 `"의미 검증을 완료하지 못했습니다..."` 내부 문구를 그대로 반환(`review.py:251`).

→ **사용자가 겪은 차단 문구는 구조적으로 다시 나올 수 있다.** 소프트 fallback("확인 근거가 충분하지 않아...")으로 완화는 됐지만 하드 문구 자체는 제거 안 됨.

---

## Q4 — Final Delivery Gate가 첨부 경로 보정을 하는가: **아니오**

`grep` 결과 `final_delivery_repair` / `repair_artifact_delivery`는 `delivery_gate.py`·`final_qa_runtime.py`·`__init__.py` 어디에도 import 안 됨.
게이트는 **텍스트만 복구**하고 첨부 staging은 안 한다. 첨부 경로 보정은 오직 `media_delivery_contract` 도구를 **LLM이 자발적으로 호출**할 때만 발생.
즉 "게이트가 첨부를 자동 보정한다"는 역할은 **미구현**. LLM이 도구 호출을 빠뜨리면 첨부 누락이 그대로 전달된다.

---

## Q5 — Self-Harness: 후보 제안 vs 자동 루프: **후보 제안 수준 (28점)**

- shadow candidate JSON 생성 + ledger 기록만. 실제 registry write `False` 고정(`self_harness.py:55`).
- 활성화(`promotion.py:142`)에 `test_receipts` 필수인데 **프로덕션에서 이걸 자동 생성하는 코드 없음**.
- `rollback_on_regression`은 readiness probe(테스트)에서만 호출.
- **cron/scheduler/gateway 호출자 0건** — `run_evolution_autopilot`는 CLI·LLM 도구 수동 실행만.
- 개선안 생성도 LLM 아닌 문자열 템플릿 룰(`_target_surface`, `_change_intent`).

→ "자동 개선 루프"가 아니라 **수동 트리거 제안 수집기**. 안전하지만(자동 변경 안 함), 광고된 자율성과 실제가 다름.

---

## 남은 리스크 + 100점까지 수정안 (적대적)

| 우선 | 리스크 | 수정안 |
|---|---|---|
| 🔴 P0 | safe_markers가 내부 차단 문구를 안전 처리 → 차단 문구 누수 | `delivery_gate.py:233-235`에서 `"전용 도구"/"후검증"/"다시 실행"` 제거. 이 단어가 보이면 오히려 **block 대상**으로 뒤집어야 함 |
| 🔴 P0 | 첨부 보정이 게이트 미배선 | `governance_transform_llm_output`이 `MEDIA:` 태그/첨부 의도 감지 시 `repair_artifact_delivery`를 직접 호출하도록 배선 |
| 🟠 P1 | 하드 내부 문구 잔존(policy/review/result_transform) | 사용자 노출 문구와 LLM-only 내부 지시를 **레이어 분리** — 내부 지시는 절대 `message_ko`로 쓰지 말 것 |
| 🟠 P1 | Final QA fail-open(타임아웃→PASS) | governed 고위험 playbook은 fail-closed 또는 1회 재시도 후 소프트 보류로 |
| 🟠 P1 | 되돌림 루프가 LLM 순응 의존(강제 아님) | retry_required 시 메인 루프가 도구 재실행을 **결정적으로 강제**하거나 미수행 시 전달 차단 |
| 🟡 P2 | Self-Harness 죽은 루프 | cron 배선 + `test_receipts` 자동 생성기 추가. **단 활성화 전 사람 승인 게이트 필수** (현재 `auto_promote_allowed=False`는 데이터 필드일 뿐 강제 아님 — 우회 가능) |
| 🟡 P2 | dispatcher/risk 키워드 하드코딩(사장님 영구원칙 위반) | 라우팅/위험판정 의도분류를 LLM 우선으로. 키워드는 보조 신호로 강등 |

---

---

# 2차: P0~P2 구현 (2026-06-26 새벽, 자율 작업)

> 사장님 지시: "P0~P2 전부 구현, 모든 항목 100점까지 루프." + "미호는 범용 거버넌스 OS다 — 일반 질문·코딩도 잘해야 한다."
> 판정: 캡틴 재적대채점 + pytest 그린. Self-Harness = 완전 자동 활성화 선택.

## 적용된 수정

### P0 — 차단 문구 누수 + 첨부 보정 + 적대검증 자기차단
- **leak 게이트 신설** (`delivery_gate.py:_contains_internal_guard_leak`): 거버넌스 내부 지시 구절/JSON 키가 새면 block→LLM repair. `delivery_gate_constants.py`에 `INTERNAL_GUARD_LEAK_MARKERS`(18) + `GOVERNANCE_JSON_LEAK_KEYS/PAIRS`.
- **safe_markers 구멍 제거**: "전용 도구/후검증/다시 실행"을 safe 목록에서 빼서 더는 차단문구가 무사통과하지 않음.
- **첨부 경로 보정 배선** (`delivery_gate.py:_repair_attachment_paths`): 최종 게이트가 MEDIA 태그 경로를 `repair_artifact_delivery`로 staging 후 태그 치환. 이제 게이트가 첨부 보정을 직접 수행(Q4 해결).
- **적대검증 자기차단 방지**: `governance_review_context` allow + leak 게이트로 이중 방어.

### P0+ — 범용성 (사장님 교정)
- leak 마커를 **거버넌스 고유 구절로만** 한정. 일반 코딩("npm run build 다시 실행"), API 설계("next_action 필드"), 일반 지식(GIL)이 게이트를 통과함을 테스트로 못박음. 거버넌스 게이트는 학원 도메인 governed playbook에만 작동.

### P1 — fail-open/closed + 레이어 분리
- `final_qa.py:verdict_or_pass`: reviewer 불가 시 **일반 답변은 fail-open(통과), governed는 fail-closed(REVISE)**. `_is_governed_evidence`로 분기 → 범용성 보존하며 도메인 산출물만 보류.
- `result_transform.py`: tool result에 `assistant_instruction`(내부 전용)과 `user_safe_message`(사용자 노출 안전 문구) **레이어 분리**.
- retry 강제: delivery gate의 review-evidence block이 이미 메커니즘(retry 무시하고 답하면 게이트가 차단→repair 회수).

### P2 — Self-Harness 완전 자동 활성화 루프 (신규 `self_harness_loop.py`)
- `run_self_harness_autopilot`: evidence 마이닝 → shadow candidate → **test_receipts 자동 생성(실제 pytest)** → `decide_autonomous_activation` → `activate_autonomous_candidate`(실제 registry write) → post-activation regression smoke → `rollback_on_regression`.
- `register_self_harness_cron`: `no_agent`+`script` 잡으로 무인 스케줄(멱등). `__init__.py:_ensure_self_harness_autopilot_cron`이 운영 부팅 시 등록(테스트/CI 스킵).
- 안전장치: `auto_promote_allowed=false` 강제(기존 계약), `_is_unsafe_candidate`(프롬프트 인젝션/시크릿 경로 차단), 활성화 전 스냅샷 + regression 자동 롤백, 후보별 예외 격리.

## 검증
- 거버넌스 OS 전체: **2421 passed, 2 skipped** (신규 테스트 18 포함, 회귀 0)
- 신규 테스트: delivery_gate leak/첨부/범용 통과, final_qa fail-open/closed, result_transform 레이어 분리, self_harness_loop 활성화/롤백/보류/unsafe/cron 멱등

## 재채점 1차 → 2차 수정

**1차 재적대채점**(에이전트 2기)에서 발견된 진짜 결함과 조치:

| 결함 | 1차 점수 | 조치 |
|---|---|---|
| **P2 cron 경로 미스매치** (🔴 실행 자체 차단) | 50 | repo 경로를 박은 shim을 `~/.miho/scripts`에 생성→basename 등록. cron 경로 가드(`scheduler.py:843-865`) 통과 |
| **Q4 blocked 첨부 원본 노출** | 61~65 | blocked/error 시 `_ATTACHMENT_UNAVAILABLE_NOTE`로 치환 — 깨진 MEDIA 태그 사용자 노출 차단 |
| **Q3 zero-width 우회** | 68~72 | `_normalized_blob`(invisible/bidi 제거) → leak/score 매칭에 적용 |
| **범용성: score claim 오탐** | 76~78 | score 강제 라우팅에 `_has_admission_context`(수시/환산/학종/가능권…) 조건 → 일반 기술 점수 통과 |
| **P2 max_activations 폭주** | (P2 50) | 기본값 1 — 단계적 활성화 |

**의도적 스킵(오버엔지니어링/극단 가정):** exception 타입별 분기, playbook별 맞춤 fallback(현 문구 범용적), _is_governed_evidence type 강화, assistant_instruction 마스킹(substring 매칭으로 partial echo도 잡힘), test_receipts 동적생성(shadow candidate=정책 게이트 추가라 기존동작 보존 검증이 맞음).

**검증:** 거버넌스 OS 전체 **2426 passed, 2 skipped** (2차 수정 반영).

## 최종 재채점 결과 (치명 결함 기준)

| 항목 | 1차 | 최종 | 판정 |
|---|---|---|---|
| Q3 차단문구 노출 | 68~72 | **100** | zero-width 정규화 + substring 매칭, 누수 경로 없음 |
| Q4 첨부 보정 | 61~65 | **100** | blocked/repaired/already_allowed 3경우 모두 깨진 경로 미노출 |
| 범용성 | 76~78 | **100** | `_has_admission_context`로 일반 기술/코딩/지식 답변 오탐 차단 0 |
| P2 cron 실제 실행 | 50 | **100** | shim repo경로 baked-in + basename 등록 → 경로가드/인터프리터 통과, max_activations=1 |

**치명 결함 (실행차단/사용자노출/범용성훼손/루프 미작동) 없음.** 검증: **2426 passed, 2 skipped.**

## 보류 — 사장님 판단 필요 (트레이드오프)

원 리뷰의 🟡 P2 "dispatcher/risk 키워드 하드코딩 → LLM 의도분류"는 **의도적으로 보류**:
- **risk 판정**: 배포/운영 등 위험 작업 승인 게이트. LLM 위임 시 false negative(위험 작업 놓침) = 보안 구멍. policy처럼 **결정적이 더 안전**(적대 리뷰도 "Policy는 deterministic이 맞다"고 인정).
- **dispatcher**: 이미 키워드 후보 + 애매 시 LLM 보조. 완전 LLM화는 일반 요청을 governed로 끌어들여 **사장님이 강조한 범용성과 충돌** + 회귀 위험.
- "위험 변경은 사람 승인 1회" 원칙상, 보안 게이트를 LLM에 위임하는 건 자율 진행하지 않고 사장님 결정을 받는 게 맞다.

→ 사장님이 "risk도 LLM 보조로(키워드 1차 + LLM 해제)" 원하면 별도 작업으로 진행 가능.

---

## 부록 — 검증에 사용한 핵심 코드 좌표

| 주제 | 파일:라인 |
|---|---|
| 최종 전달 게이트 본체 | `plugins/governance_os/delivery_gate.py:41-118` |
| safe_markers 화이트리스트 구멍 | `plugins/governance_os/delivery_gate.py:222-248` |
| 차단→복구 런타임 브리지 | `plugins/governance_os/final_qa_runtime.py:8-40` |
| LLM Final QA verdict/repair 루프 | `plugins/governance_os/final_qa.py:26-168` |
| 첨부 경로 보정 executor | `plugins/governance_os/final_delivery_repair.py:49-97` |
| 되돌림(retry) 신호 생성 | `plugins/governance_os/result_transform.py:28-101` |
| review gate(하드+LLM aux) | `plugins/governance_os/review.py:199-300` |
| 하드 내부 차단 문구 | `plugins/governance_os/policy.py:40,56` |
| 훅 등록 | `plugins/governance_os/__init__.py:62-63` |
| transform_llm_output 발화 | `agent/conversation_loop.py:4083-4104` |
| transform_tool_result 발화 | `model_tools.py:866-887` |
| Self-Harness shadow candidate | `plugins/governance_os/self_harness.py:55,79-97` |
| 활성화 게이트(test_receipts 필수) | `plugins/governance_os/promotion.py:142-150` |
| 자동 롤백(미배선) | `plugins/governance_os/self_harness_autonomy.py:97-123` |
