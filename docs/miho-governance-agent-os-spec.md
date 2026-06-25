# Miho Governance Agent OS 실행 명세

## 목표

미호를 단순 챗봇이나 도구 묶음이 아니라, 요청을 이해하고, 도구를 강제하고, 결과를 검수하고, 실패를 기록하고, 반복 실패를 운영 규칙으로 승격하며, 언제든 롤백 가능한 전용 Agent OS로 만든다.

이 명세는 MVP가 아니라 최종형을 향한 production-grade milestone 기준이다. 각 단계는 독립 배포 가능해야 하지만, 장난감 단계로 멈추지 않는다.

## 현재 자산

- `decision_twin`: Discord 요청을 읽고 의도, route, required_tool 힌트를 만든다.
- `academy_result_reviewer`: 학종 PDF, 실기 추천, 수시 산식/환산점수, 생기부 결과를 전달 전 검수한다.
- `media_delivery_contract`: 생성된 파일을 Discord/gateway 첨부로 보내기 전 경로, `MEDIA:` 지시, reviewer payload를 검증한다.
- `pre_tool_call`: 생기부/수시/PDF를 직접 코드로 우회 생성하는 시도를 막는다.
- `transform_tool_result`: 도구 결과를 사용자에게 전달하기 전에 재작성하거나 차단한다.
- `transform_llm_output`: governed playbook으로 라우팅되는 응답이 전용 도구와 reviewer pass evidence 없이 전달되는 것을 막는다.
- `transform_llm_output`은 원 사용자 문장 또는 응답 본문이 governed playbook으로 잡히면, 안전한 비전달 안내가 아닌 한 완료/첨부/점수/PDF 키워드 추정 없이 기본 차단한다.
- `Evolution OS`: 실패 패턴, 제안, promotion, rollback, harness rule을 JSONL로 기록한다.
- `PluginManager`: backend 플러그인을 기본 로드하고, 플러그인별 auxiliary task를 선언할 수 있다.
- `plugin.yaml`: Governance OS가 제공하는 hook과 auxiliary task를 함께 선언해 운영/doctor/readiness가 등록 결과와 대조할 수 있다.

## 최종 구조

Governance OS는 기존 플러그인을 대체하지 않고, 다음 계층을 일반화한다.

```text
User Request
-> Dispatcher
-> Playbook Registry
-> Policy / Tool Contract Guard
-> Worker Tool or Domain Agent
-> Result Review Gate
-> Outcome Ledger
-> Promotion Pipeline
-> Drill / Simulator
```

### Agent Council

Council은 항상 여러 모델을 병렬 호출한다는 뜻이 아니다. 책임이 분리된 판단 단위를 뜻한다.

- `dispatcher`: 요청을 업무 유형과 playbook으로 매핑한다.
- `risk_judge`: 승인, 민감정보, 외부 전송, 운영 변경 위험을 판정한다.
- `tool_contract_guard`: playbook의 required_tools와 forbidden_tools를 강제한다.
- `result_reviewer`: 산출물 품질, 산식, 레이아웃, 의도 일치를 검수한다.
- `ledger_writer`: 결과, 실패, 검수 상태, 사용자 피드백을 append-only로 남긴다.
- `promotion_judge`: 반복 실패를 규칙 후보로 승격할지 판정한다.
- `drill_runner`: 가짜 요청과 회귀 케이스로 라우팅/검수/승격 루프를 훈련한다.

### Domain Agent Packs

도메인 에이전트는 범용 OS 위에 얹는 pack이다. 처음부터 모든 도메인을 같은 코드에 섞지 않는다.

- `academy`: 생기부, 학종, 수시, 실기 추천, 학원 운영.
- `dev`: 코드 변경, 테스트, 배포, 롤백, 문서화.
- `research`: 웹/문서/유튜브/GitHub 조사와 출처 검증.
- `discord_ops`: 첨부, 채널/스레드 정책, 사용자 권한, 메시지 전달.
- `memory`: 사용자 교정, 업무 판례, 장기 기억 승격.

## 핵심 계약

### AgentRole

```text
key
kind: control | judge | worker | domain
description
responsibilities
allowed_tools
forbidden_tools
review_gates
timeout_seconds
fallback_agent
```

### Playbook

```text
key
domain
triggers
required_context
required_tools
forbidden_tools
agent_chain
review_gates
retry_policy
delivery_format
ledger_policy
memory_policy
rollback_policy
```

### PolicyDecision

```text
action: allow | block | review_required | retry | require_approval
reason
playbook_key
agent_key
tool_name
message_ko
evidence
```

사용자-facing 메시지는 한국어 평문이어야 한다. 400/401/CORS, stack trace, Python 예외명, 내부 hook 이름을 그대로 노출하지 않는다. `governance_os` 운영 도구의 오류도 같은 기준을 따른다.

### OutcomeLedgerEntry

```text
request_id
playbook_key
agent_chain
tools_used
duration_ms
review_status
failures
artifact_paths
user_feedback
promotion_candidates
created_at
```

Outcome ledger는 Evolution OS와 연결하되, 기존 `events.jsonl`의 의미를 깨지 않는다. 작업 결과는 `note` 또는 별도 metadata로 시작하고, 반복 실패만 proposal/promotion 후보가 된다.

## Runtime Flow

1. `pre_gateway_dispatch`에서 dispatcher가 request summary와 playbook 후보를 만든다.
   생기부/학생부 첨부 자동 감지는 직접 저장 응답을 만들지 않고 항상 `life_record_ingest_pdf` visible tool call로 rewrite한다.
2. deterministic trigger confidence가 높으면 fast path를 유지하고, 복합/애매한 요청이면 `miho_governance_dispatcher` auxiliary task를 호출해 playbook을 재판정한다.
3. auxiliary dispatcher가 실패하거나 invalid JSON을 반환하면 내부 오류를 사용자에게 노출하지 않고 deterministic fallback으로 진행한다.
4. playbook이 결정되면 `risk_judge`가 운영 변경, 민감정보, 외부 전송 위험을 먼저 판정한다.
5. 승인 필요 요청은 `pre_gateway_dispatch`에서 즉시 한국어 승인 대기 응답으로 돌려보내고, LLM/tool 실행 경로로 넘기지 않는다.
6. 승인/위험 판정 뒤 required/forbidden tool contract를 turn context에 붙인다.
7. dispatcher는 `missing_context`가 있으면 전용 도구 호출 전에 누락 정보를 안전하게 추론하거나 한국어로 명확히 질문하도록 rewrite한다.
8. `pre_tool_call`에서 tool contract guard가 우회 도구를 차단한다.
9. domain worker가 전용 도구를 실행한다.
10. `transform_tool_result`에서 review gate가 deterministic check와 auxiliary reviewer를 순서대로 돈다.
11. governed self-reviewed tool 결과는 schema pass 뒤에도 `semantic_review_required` flag 유무와 무관하게 `miho_governance_reviewer` auxiliary task로 의미 검증을 실행한다. flag는 자동 정책 경로의 추가 신호일 뿐, academy/attachment 핵심 도구의 검수 우회 조건이 아니다.
12. auxiliary reviewer가 실패하거나 invalid JSON을 반환하면 내부 provider 오류를 노출하지 않고 한국어 fail-closed 메시지와 `retry_tools`를 반환한다.
13. 파일 첨부 산출물은 `media_delivery_contract`가 백틱으로 감싼 `MEDIA:` 지시를 생성해 xlsx, mhtml 같은 확장자도 gateway 첨부 경로를 탄다.
14. 실패하면 사용자에게 최종 산출물처럼 말하지 않고, 같은 전용 도구 재시도 지시와 구조화된 `retry_tools`를 반환한다.
15. 성공/실패 모두 ledger에 남기고 `governance_os`의 `outcomes` 액션에서 조회한다.
16. 반복 실패가 기준을 넘으면 promotion candidate로 제안하고 `governance_os`의 `promotions` 액션에서 확인한다.
17. promotion은 검증, 테스트, rollback 경로가 있을 때만 active rule이 된다.
18. readiness/status probe는 운영 장부를 오염시키지 않는다. probe는 별도 recorder나 non-mutating 실행 경로로 검증한다.

## Production Milestones

### M1 Foundation

- Governance spec 고정.
- `plugins/governance_os` backend 플러그인 생성.
- AgentRole, Playbook, PolicyDecision 스키마와 registry 구현.
- 기본 playbook seed 작성.
- runtime behavior는 바꾸지 않고 로드/검증/보조 task 등록만 확인한다.

### M2 Policy Guard

- academy hardcoded guard를 playbook 기반 정책으로 부분 이전한다.
- forbidden tool block 메시지는 한국어 평문으로 통일한다.
- 수시/학종/실기/생기부 우회 생성 시 전용 도구만 허용한다.
- risk judge는 배포, 재시작, 마이그레이션, credential, 민감 memory 저장 요청을 승인 필요 상태로 보류한다.
- guard는 `terminal` 같은 일반 도구의 args 내부에 들어간 금지 명령(`git reset --hard`, `git checkout --`)도 차단한다.

### M3 Review Loop

- academy result reviewer를 generic review gate API에 연결한다.
- PDF 레이아웃, 산식, 근거 도구, 학생명/학교명, media_tag 계약을 검수한다.
- `academy_result_reviewer`가 pass를 주더라도 의미 있는 checked 묶음이 없으면 generic review gate는 fail 처리한다.
- fail이면 같은 playbook 재시도 지시와 `retry_tools`가 ledger와 tool result에 남는다.
- review fail 결과는 사용자용 오류 문구와 분리된 내부 `retry_instruction_ko`를 함께 내려, 모델이 `retry_tools`의 전용 도구를 다시 실행하도록 한다.
- academy reviewer bridge도 blocked/failed outcome을 Evolution ledger에 기록할 때 source tool을 `retry_tools`로 남긴다.

### M4 Outcome Ledger

- request_id 단위 outcome entry를 기록한다.
- 사용 도구, 실패 횟수, reviewer status, artifact path, user feedback을 남긴다.
- Evolution OS와 안전하게 연결한다.
- `governance_os` 운영 도구는 `outcomes` 액션으로 최근 outcome과 playbook 필터 조회를 지원한다.

### M5 Promotion Pipeline

- 반복 실패를 playbook rule, tool contract, reviewer policy 후보로 승격한다.
- Outcome ledger의 `governance_outcome` 실패를 playbook/failure 단위로 묶어 promotion candidate를 제안한다.
- `governance_os` 운영 도구는 `promotions` 액션으로 후보, evidence, required tests, rollback 경로를 반환한다.
- `governance_os` 운영 도구는 `promote` 액션으로 evidence, required tests, 구조화된 test receipts, rollback path가 있는 후보만 active registry rule로 승격한다.
- `promote`는 문자열 테스트 통과 주장만으로는 승격하지 않고, 각 required test와 매칭되는 `name`, `command` 또는 `evidence`, pass 상태를 가진 receipt를 요구한다.
- promotion test receipt의 `name`은 required test path 또는 pytest nodeid와 정확히 매칭되어야 하며, path를 포함한 임의 문자열은 통과 증거가 아니다.
- promotion은 evidence, test plan, rollback path가 없으면 active가 될 수 없다.
- promotion candidate의 required tests는 playbook과 failure 유형을 함께 반영한다. 예를 들어 `forbidden_tool` 반복 실패는 policy/drill 검증을, `reviewer_missing` 반복 실패는 review/council 검증을 요구한다.
- active rule rollback이 가능해야 하며 rollback ledger는 되돌린 promotion event id, promoted snapshot, rollback snapshot을 함께 남긴다.
- `governance_os activate`는 structured runtime verification receipts와 rollback plan 없이는 snapshot을 active로 전환하지 않는다.
- `governance_os rollback`은 promotion rollback snapshot이면 즉시 허용하고, 그 외 snapshot 전환은 structured runtime verification receipts와 rollback plan을 요구한다.

### M6 Simulator / Drill

- 학종 PDF, 실기 추천, 수시 산식, 생기부 저장, Discord 첨부, dev deploy 가짜 요청을 재생한다.
- 각 drill은 도구 선택, 금지 도구 차단, review fail/retry, ledger 기록을 검증한다.

### M7 Domain Packs

- academy pack을 먼저 완성한다.
- dev, research, discord_ops, memory pack은 같은 registry 계약으로 확장한다.
- pack별 reviewer와 drill suite를 둔다.
- `governance_os` 운영 도구는 `packs` 액션으로 domain agent, playbook, required tool, reviewer coverage를 조회한다.
- academy pack은 학종, 실기 추천, 생기부 저장뿐 아니라 수시 점수계산/내신환산 단독 요청도 `susi27_score_calculate` playbook으로 라우팅한다.
- readiness는 domain pack coverage를 포함해 누락된 domain agent나 playbook 연결을 배포 전 차단한다.
- readiness는 review failure가 구조화된 `retry_tools`를 반환하는지도 probe로 확인한다.
- readiness는 review failure가 `next_action=retry_required`, 내부 `retry_instruction_ko`, 사용자용 오류 비노출 계약을 지키는지도 probe로 확인한다.
- readiness는 `governance_os.register(ctx)`가 `pre_gateway_dispatch`, `pre_tool_call`,
  `transform_tool_result` 훅과 dispatcher/reviewer/promotion judge 보조 task를 실제 등록하는지도 확인한다.
- readiness는 `plugin.yaml`의 `provides_hooks`와 `provides_auxiliary_tasks`가 실제 등록 훅/보조 task를 모두 선언하는지도 확인한다.
- readiness는 PluginManager가 Governance OS를 enabled 상태로 로드했고 실제 hook callback과 보조 task를 보유하는지도 확인한다.
- readiness는 promotion candidate의 required tests가 playbook/failure 유형별 focused safety tests를 요구하고 registry-only foundation test로 후퇴하지 않는지도 확인한다.
- readiness는 dispatcher/reviewer/promotion judge 보조 task가 역할별 운영 지침을 defaults에 보유하는지도 확인한다.
- readiness는 애매한 라우팅이 `miho_governance_dispatcher` data-plane으로 넘어갈 수 있는지 확인하되, probe fake transport를 인자로 주입해 production `agent.auxiliary_client` 전역 함수를 바꾸지 않는다.
- readiness는 governed reviewer pass가 `miho_governance_reviewer` data-plane으로 넘어갈 수 있는지 확인하되, probe fake transport를 인자로 주입해 운영 호출 경로와 충돌하지 않는다.
- readiness는 self-reviewed tool transform이 성공/실패 outcome을 ledger 계약에 맞게 만들되, readiness 실행 자체는 ledger를 쓰지 않는지도 확인한다.
- readiness는 final delivery gate가 current-turn reviewer pass evidence 없는 governed 응답을 차단하고 pass evidence가 있으면 허용하는지도 확인한다.
- readiness는 임시 `MIHO_HOME`에서 Evolution OS의 skill snapshot rollback과 harness rule rollback 경로를 실제로 실행해 rule/skill rollback 계약을 증명한다.
- final delivery gate는 최근 global ledger pass를 현재 요청 증거로 재사용하지 않고, 명시적으로 전달된 current-turn outcome만 신뢰한다.

### M8 Runtime Operations

- gateway restart 전 smoke test와 rollback plan을 자동 체크한다.
- `governance_os preflight`는 로컬 검증 receipt(source, timestamp, command hash), runtime smoke receipts, config checks, rollback plan, readiness 100점을 모두 요구하고 문자열 주장이나 status-only dict만으로는 통과하지 않는다.
- 운영 상태는 Discord/Telegram 완료 보고와 로컬 로그에 남긴다.
- production restart는 테스트, config 확인, rollback 경로 없이는 진행하지 않는다.

## 품질 기준

- 새 runtime 파일은 500줄 이하.
- 새 기능은 테스트 먼저 작성하고 실패를 확인한다.
- 기존 `decision_twin`, `academy_result_reviewer`, `Evolution OS`를 끊지 않는다.
- 사용자에게 전달되는 차단/오류 문구는 한국어 평문.
- frontend/API contract가 있는 변경은 browser-facing smoke path를 포함한다.
- 배포 전 `git diff --check`, focused tests, 관련 wider tests를 통과한다.
- 실패한 검증은 ledger나 테스트 출력으로 추적 가능해야 한다.

## 완료 정의

Governance Agent OS가 “완성”으로 판정되려면 다음이 모두 참이어야 한다.

- 범용 dispatcher가 playbook을 선택한다.
- tool contract guard가 전용 도구 우회를 막는다.
- reviewer가 도메인 산출물을 차단/통과/재시도 시킬 수 있다.
- outcome ledger가 모든 고위험 요청의 성공/실패를 기록한다.
- promotion pipeline이 반복 실패를 검증된 active rule로 승격한다.
- rollback이 rule, skill, playbook 단위로 가능하다.
- drill suite가 주요 도메인 회귀를 자동 재생한다.
- 실제 gateway smoke에서 Discord 요청, 도구 호출, 결과 검수, 첨부 전달이 통과한다.
