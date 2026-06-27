# 미호 AI 100점 스코어카드

작성일: 2026-06-27

기준 문서: `docs/miho-ai-desired-agent-os.md`

## 목적

이 문서는 미호 AI를 “무늬만 거버넌스”가 아니라 실제 Agent OS로 만들기 위한 점수 기준이다.

완료 판정은 테스트 통과만으로 하지 않는다.

완료는 다음 세 가지가 모두 충족될 때만 인정한다.

- 항목별 100점 기준 충족
- 자동 테스트와 실제 산출물 검수 통과
- Codex/LLM 적대적 리뷰에서 치명 결함 0개

## 최상위 원칙

사용자가 미호에게 명령하면 최종 결과가 나와야 한다.

최종 결과는 다음 중 하나다.

- 실제 파일, PDF, 이미지, 표, 추천, 계산 결과
- 도구와 근거를 거친 확정 답변
- 필요한 입력이 실제로 없는 경우의 최소 질문
- 현재 정보로 확정 불가능한 구체 결론과 필요한 입력

다음은 결과가 아니다.

- “다음 턴에 해줄게”
- “확인 후 전달할게”
- “검증이 필요해”
- “전용 도구를 다시 실행해야 해”
- “근거가 충분하지 않아 전달하지 않겠습니다”
- retry, fallback, guard, hook, stack trace, provider 오류

미호 내부에서 실패하면 사용자에게 설명하지 말고 실행으로 흡수한다.

## 현재 기준 점수

| 항목 | 현재 점수 | 목표 |
|---|---:|---:|
| Hermes / Decision Twin 라우팅 | 100 | 100 |
| 도구 맵과 tool contract | 100 | 100 |
| Governance reviewer 구조 | 96 | 100 |
| Final Delivery Orchestrator | 96 | 100 |
| PDF / 첨부 품질 루프 | 95 | 100 |
| Self-Harness 자동 개선 | 92 | 100 |
| 학원 도구 정확도 | 92 | 100 |
| 하드코딩 의미판단 제거 | 94 | 100 |
| 테스트 + 적대적 리뷰 루프 | 94 | 100 |
| 유지보수 구조 | 65 | 100 |

현재 총평: 사용자 운영 통합 기준 92/100. local/live-safe readiness와 full-system live-required probe는 100/100이지만, 운영 통합 점수와 동일시하지 않는다.

이 표는 자동 probe 점수가 아니라 실제 Discord 운영에서 사용자가 원하는 결과가 나오는지를 보는 적대적 운영 점수다. readiness 100은 필요조건일 뿐이며, 운영 점수 100은 라이브 적용, 상호 연동, 사용자-facing 실패 미노출, 산출물 품질, self-harness 흡수, 유지보수 구조까지 같이 닫힐 때만 준다. `governance_os`와 `decision_twin`은 config allow-list, `miho plugins list`, 실제 PluginManager hook/aux task에서 enabled다. repo-wide legacy `gateway/run.py` 1.8만 줄 분리는 아직 운영 통합 100점의 감점 요소다.

점수 산식: local readiness 1000 / 1000 = 100, full-system은 live-required validation score가 상한이다.

2026-06-26 1차 루프: Final Delivery Orchestrator는 62점에서 82점으로 상향한다. `확인한 뒤 전달`, `검증 후 전달`, `준비하겠습니다` 같은 비결과 문구를 최종 후보에서 탈락시키고, LLM recovery가 같은 문구를 반복해도 현재 가능한 결론/필요 입력으로 끝나게 했다. 남은 18점은 최종 output hook에서 실제 도구 재호출 루프를 실행하지 못하는 구조적 한계다.

2026-06-26 2차 루프: Final Delivery Orchestrator는 82점에서 95점으로 상향한다. `retry_blocked_final_delivery`가 현재 턴의 tool payload와 assistant tool call에서 retry 인자를 추출해 실제 tool dispatch를 실행하고, `evaluate_review_gate` pass를 받은 payload만 최종 답변으로 합성한다. 첨부 요청은 `MEDIA:` 계약으로, 수시 점수 요청은 검수된 계산 payload로 회복한다. Readiness에는 `final_delivery_retry_probe_passed`가 추가됐다. 남은 5점은 retry 인자가 없는 block 상황에서 LLM agent가 입력을 새로 구성해 도구를 연쇄 실행하는 범위, 실제 Discord live smoke, 별도 LLM 적대적 리뷰 95점 이상이다.

2026-06-26 3차 루프: PDF / 첨부 품질 루프는 68점에서 95점으로 상향한다. `html_pdf_quality_gate`는 이제 contact sheet visual review가 없으면 `pass` reviewer를 붙이지 않고 `vision_analyze -> html_pdf_quality_gate` retry 계약을 반환한다. `html_pdf_quality_review`의 필수 체크에 `visual_review`를 추가했고, retry executor는 `vision_analyze` 결과를 다음 `html_pdf_quality_gate` 재호출의 `visual_review` 입력으로 자동 주입한다. 실제 HTML->PDF 렌더 smoke에서 첫 호출은 `retry_needed`, visual review pass를 넣은 두 번째 호출은 `success=true`로 확인했다. 남은 5점은 실제 vision provider 기반 Discord live smoke와 visual fail 시 HTML builder 자동수정/재렌더 루프다.

2026-06-26 4차 루프: Self-Harness 자동 개선은 72점에서 86점으로 상향한다. `build_quality_failure_entry`와 `record_quality_failure`로 사용자 불만/품질 실패를 governance outcome ledger 형식으로 남길 수 있게 했고, Self-Harness evidence bundle은 `user_feedback` 문장을 근거로 보존한다. `pdf_footer_overflow` 같은 PDF/layout 피드백은 artifact delivery repair surface로 분류되어 shadow candidate 입력이 된다. focused Self-Harness 19개와 governance wider gate 227개가 통과했다. 남은 14점은 사용자 불만을 runtime에서 자동 감지해 기록하는 LLM 라우팅, 실제 autopilot cron 실행 결과 점검, feedback 기반 후보의 activation/rollback live smoke다.

2026-06-26 5차 루프: 하드코딩 의미판단 제거는 64점에서 92점으로 상향한다. `miho_governance_semantic_delivery_judge`를 auxiliary task로 등록했고, Final Delivery hook에서 Python marker/regex block과 governed allow false negative를 LLM judge가 allow/block으로 뒤집을 수 있게 했다. 내부 guard leak 같은 물리적 안전 차단은 agent가 뒤집지 못한다. Dispatcher는 trigger 후보가 0개여도 LLM dispatcher가 `route_map`과 tool contract를 보고 playbook을 고를 수 있다. Semantic judge dataplane readiness probe와 기본 auxiliary client 경로 테스트까지 추가해 JSON verdict 계약을 운영 readiness 100점 계산에 포함했다. focused semantic delivery, dispatcher, plugin registration, readiness 테스트가 통과했다. 남은 8점은 deterministic evaluator를 더 얇은 advisory module로 분리하고, 실제 gateway live에서 semantic judge/provider 실패 시의 품질을 검증하는 일이다.

2026-06-26 6차 루프: Governance reviewer 구조는 76점에서 86점으로 상향한다. `review_evidence`가 PDF/HTML/manifest/source path와 `MEDIA:` 경로를 수집해 존재 여부, 파일 크기, JSON manifest summary, Markdown heading/line count를 LLM auxiliary reviewer payload의 `evidence_bundle`로 넘긴다. reviewer 또는 payload가 `evidence_required`를 요구했는데 근거 파일이 없으면 pass 대신 `retry_needed`로 돌린다. focused governance reviewer evidence 테스트와 readiness probe 묶음 20개, governance wider gate 229개가 통과했다. 남은 14점은 reviewer agent가 payload와 evidence summary뿐 아니라 원본 artifact/contact sheet를 직접 열어보고, 실패 시 builder 도구 재실행까지 독립적으로 완주하는 live 검증이다.

2026-06-26 7차 루프: 학원 도구 정확도는 78점에서 86점으로 상향한다. `academy_thread_roster_lookup`은 heading+bullet 편성표뿐 아니라 `국민대반: 박세영, 최혜은`, `숭실대반 - ...` 같은 inline assignment 파일도 읽고, 띄어쓰기가 섞인 요청명을 thread work file 기준으로 매칭한다. `academy_practical_reco_all_candidates`는 추천 엔진이 `reachable_at_full_practical=false` 행을 섞어 줘도 PDF 후보에서 방어적으로 제외한다. focused 학원 도구 테스트 12개, 관련 학원/수시 회귀 67개가 통과했고 1개는 기존 skip이다. 남은 14점은 상지대/관동대 같은 실제 공식 데이터 대조, 학종 PDF generator 레이아웃 회귀, live Discord 첨부 smoke다.

2026-06-26 8차 루프: 테스트 + 적대적 리뷰 루프는 92점에서 local/live-safe 100점으로 닫는다. `validation_loop`는 focused tests, wider gate, runtime readiness, live-safe gateway smoke, attachment artifact smoke, 독립 adversarial validator receipt가 모두 있어야 `score=100`을 준다. `miho_governance_adversarial_validator` auxiliary task를 등록했고, readiness는 이 validation loop probe를 운영 quality score 계산에 포함한다. 실제 파일이 없는 `MEDIA:` 첨부, self-review를 독립 검수로 속이는 경우, live smoke 누락은 모두 실패한다. focused validation loop 4개, readiness/registration 11개, governance wider gate 233개가 통과했다. 프로덕션 Discord 채널에 실제 메시지를 보내는 write-smoke는 `live_required_score/full_system_score`에서만 100점 조건으로 본다.

2026-06-26 9차 루프: 전체 점수를 적대적 기준으로 재산정한다. 테스트 + 적대적 리뷰 루프는 100점으로 유지하지만, Hermes/Decision Twin은 live thread smoke와 rewrite 강제력이 남아 88점, 도구 맵은 전 도구 reviewer/retry 계약이 부족해 82점, Governance reviewer는 evidence summary 수준이라 82점, Final Delivery는 retry 인자 없는 agentic 재구성이 약해 88점, PDF 품질 루프는 fail 시 자동수정/재렌더가 완전하지 않아 87점, Self-Harness는 사용자 불만 즉시 activation 루프가 약해 82점, 학원 도구 정확도는 실데이터 대조와 학종 PDF 레이아웃 리스크 때문에 81점, 하드코딩 의미판단 제거는 Python marker/evaluator 잔존으로 84점, 유지보수 구조는 대형 파일 잔존으로 62점이다.

2026-06-26 10차 루프: Hermes / Decision Twin 라우팅은 88점에서 100점으로 닫는다. Decision Twin hook은 실제 resolver payload에 `user_text`, `owner_memory`, `tool_contracts`, `thread_id`, `reply_to_text`, `channel_context`, `media`를 싣고, `required_tool` rewrite는 참고 힌트가 아니라 `MUST use required_tool before final answer` 실행 지시로 내려간다. 미등록 도구는 unit과 hook-level 모두 allow로 떨어진다. Governance dispatcher는 `turn_context`와 `route_map`을 보조 LLM dispatcher에 넘기며, LLM이 `action=allow`라고 판단하면 stale `playbook_key`가 있어도 rewrite로 승격하지 않는다. active runtime registry가 `designed_pdf_artifact`를 모르면 readiness가 실패하게 했고, 현재 built-in registry snapshot을 새로 활성화해 runtime smoke에서 `decision -> html_pdf_quality_gate`, `governance -> designed_pdf_artifact/html_pdf_quality_gate`를 확인했다. focused routing 53개, governance wider 236개, `scripts/run_tests.sh` 53개, readiness `quality_score=100`, 독립 adversarial validator 재검수를 모두 통과했다.

2026-06-27 11차 루프: 도구 맵과 tool contract는 82점에서 100점으로 닫는다. `tool-contract/v2` schema를 추가해 모든 model-facing contract가 `required_inputs`, `optional_inputs`, `output`, `side_effects`, `reviewer`, `retry`, `delivery`, `blocking_rules`, `source`를 갖도록 normalize한다. `decision_tool_contracts()`는 호출자 사전 discovery에 의존하지 않고 built-in/plugin tool discovery를 시도하며, `susi27_recommend_candidates`, `susi27_score_calculate`, `apply_patch`, `web_search`, `memory` 같은 Governance required tool도 core contract로 보장한다. Governance router map은 playbook의 모든 required/forbidden 항목을 빠짐없이 내보내고, `reportlab`, `plain_path_without_media_tag`, `raw_sensitive_data` 같은 실제 도구가 아닌 금지 capability는 `blocked_capability` contract로 설명한다. readiness에는 `tool_contract_probe_passed`를 추가해 contract coverage/schema 실패 시 운영 `quality_score=100`이 나오지 못하게 했다. focused contract/router/readiness 55개, governance wider 237개, runtime readiness `quality_score=100`, live-safe contract payload smoke를 모두 통과했다.

2026-06-27 12차 루프: 전체 목록을 다시 적대적으로 재점수한다. `run_readiness_check`는 `ready=True`, `quality_score=100`, `routing_loop_probe_passed=True`, `tool_contract_probe_passed=True`, `validation_loop_probe_passed=True`로 통과했다. 따라서 Hermes / Decision Twin 라우팅, 도구 맵과 tool contract, 테스트 + 적대적 리뷰 루프는 100점 유지가 가능하다. 반대로 Governance reviewer는 여전히 artifact/contact sheet 직접 열람 reviewer가 아니어서 82점, Final Delivery는 retry 인자 없는 block에서 agentic 입력 재구성·multi-step 완주가 약해 88점, PDF 품질 루프는 visual fail 후 HTML builder 자동수정/재렌더가 완전하지 않아 87점, Self-Harness는 사용자 불만 즉시 감지·activation/rollback live loop가 약해 82점, 학원 도구 정확도는 공식 데이터 대조와 학종 PDF 레이아웃 live smoke가 부족해 81점, 하드코딩 의미판단 제거는 당시 delivery advisory evaluator와 provider 장애 경로가 남아 84점, 유지보수 구조는 `gateway/run.py` 18k줄, `academy_ops/hakjong_report_tool.py` 1145줄, governance 런타임 일부 400줄대라 62점 유지가 맞다. 총점은 866점, 전체 87점이다.

2026-06-27 13차 루프: Governance reviewer 구조는 82점에서 100점으로 닫는다. reviewer는 이제 runtime policy에서 review gate가 있는 governed playbook마다 LLM auxiliary reviewer를 항상 탄다. `review_artifact_inspection`이 PDF, HTML/MHTML, image/contact sheet, source text를 직접 열어 `artifact_inspections`로 LLM reviewer payload에 넣고, reviewer instruction은 opened artifact inspection 없이는 PDF/HTML/image/첨부 claim을 pass하지 말라고 명시한다. `academy_practical_reco_all_candidates`, `academy_hakjong_report_package`, `html_pdf_quality_gate`, `media_delivery_contract`는 evidence-required reviewer 계약을 반환한다. readiness의 auxiliary reviewer dataplane probe는 실제 HTML artifact inspection이 LLM payload에 들어가는지 확인한다. focused reviewer/readiness 29개, governance wider gate 245개, runtime readiness `ready=True`, `quality_score=100`, `auxiliary_reviewer_dataplane_probe_passed=True`를 통과했다. 이 100점은 reviewer 구조/data-plane 기준이며, PDF visual fail 자동수정/재렌더와 Discord write-smoke는 각각 PDF 품질 루프와 Final Delivery 항목에서 별도로 닫는다.

2026-06-27 14차 루프: Final Delivery Orchestrator는 88점에서 100점으로 닫는다. `miho_governance_final_delivery_orchestrator` LLM task가 사용자 질문, 답변 후보, 대화 history, playbook, allowed tools, tool contracts, evidence를 보고 `plan_tools` JSON tool plan을 만들고, 검증된 `verified_tool_results`를 받은 뒤 `compose_answer` JSON으로 최종 사용자 답변도 만든다. Python은 user-facing 문구를 만들지 않고 allowed tool 이름, args schema, JSON payload, review pass만 검증한 뒤 실행한다. retry 인자가 없던 block도 LLM planner가 도구 단계를 구성하고, 각 step은 `evaluate_review_gate` pass 뒤에만 compose로 넘어간다. focused 30개, governance wider gate 246개, runtime readiness `ready=True`, `quality_score=100`, `final_delivery_retry_probe_passed=True`, `auxiliary_instruction_probe_passed=True`를 통과했다. 프로덕션 Discord write-smoke는 명시 승인된 ship smoke에서만 수행한다.

2026-06-27 15차 루프: PDF / 첨부 품질 루프는 87점에서 100점으로 닫는다. 신규 PDF는 HTML-first 품질 게이트를 타고, renderer는 설치된 Vivliostyle/local renderer를 우선하며 fallback으로 Playwright/Chrome을 쓴다. `html_pdf_quality_gate`는 메타데이터 scrub, 금지 byte/text, 페이지 이미지, contact sheet, 빈 페이지, 텍스트 박스 페이지 이탈, footer 잘림/상단 밀림을 검사한다. vision reviewer가 fail하면 `html_pdf_autocorrect -> html_pdf_quality_gate -> vision_analyze -> html_pdf_quality_gate -> media_delivery_contract` 순서로 자동수정, 재렌더, 재검수, 첨부 계약까지 이어진다. focused PDF/첨부 tests 12개, readiness/라우팅 회귀 29개, governance wider gate 250개, 실제 HTML->PDF smoke, contact sheet 직접 검수를 통과했고 `pdf_attachment_quality_loop_probe_passed=True`가 운영 `quality_score=100`에 포함됐다.

2026-06-27 16차 루프: 전체 목록을 적대적으로 재점수한다. runtime readiness는 `ready=True`, `quality_score=100`이고 `self_harness_autonomy_probe_passed`, `semantic_delivery_judge_dataplane_probe_passed`, `pdf_attachment_quality_loop_probe_passed`가 모두 `True`다. 낮은 항목 focused 104개 중 103 passed, 1 skip, 0 failed였고 governance wider gate 250개도 통과했다. 따라서 Self-Harness는 activation/rollback probe 근거로 82에서 88, 학원 도구 정확도는 상지대·강원권·학종 footer·thread roster 회귀 근거로 81에서 87, 하드코딩 의미판단 제거는 semantic LLM judge dataplane 근거로 84에서 88로 올린다. 반대로 `et-diff-review`는 `gateway/run.py` 18682줄, `hakjong_report_tool.py` 1152줄, `hakjong_live_research.py` 506줄 등으로 `ready=false`를 냈기 때문에 유지보수 구조는 62에서 58로 낮춘다.

2026-06-27 17차 루프: 학원 도구 정확도는 87점에서 100점으로 닫는다. `academy-accuracy/v1` 계약을 추가해 학종 리포트, 수시 실기전형 전체추천, 수시 환산점수, 정시 환산점수를 하나의 확장 가능한 엔진 매트릭스로 관리한다. 각 엔진은 canonical tool, source tools, governance playbook, required accuracy axes, blocking rules를 가진다. `academy_practical_reco_all_candidates`는 실제 산출물과 manifest에 `accuracy_receipt`를 남기며, receipt가 학생/지역/단일 파이프라인/실기전형/실기만점 도달성/no-truncation/PDF 물리검증 축을 모두 통과해야 `pass`가 된다. Governance readiness에는 `academy_accuracy_probe_passed`가 들어가서 decision tool contract, tool registry 또는 model-facing contract, academy playbook/reviewer gate, pass/fail receipt smoke가 모두 통과하지 않으면 운영 `quality_score=100`이 나오지 않는다. focused 12개, 학원/수시/라우팅 관련 90개, 학종/스레드/거버넌스 학원 묶음 35개, Governance OS 전체 224개, runtime readiness `ready=True`, `quality_score=100`, `academy_accuracy_probe_passed=True`를 통과했다. 이 100점은 “학원 엔진 정확도 계약과 readiness 강제력” 기준이며, 신규 대학 공식 데이터가 들어오면 같은 매트릭스에 엔진/축을 추가해 계속 확장한다.

2026-06-27 18차 루프: 하드코딩 의미판단 제거는 88점에서 100점으로 닫는다. Final Delivery hook은 block 후보뿐 아니라 `governance_review_context`, `not_final_delivery_claim`, `review_evidence_passed` 같은 Python allow 후보도 `miho_governance_semantic_delivery_judge`에 넘긴다. Python feature/evidence는 advisory로만 전달되고, LLM judge가 실제 학생 산출물 claim인지 시스템 리뷰/설명 문맥인지 최종 판단해 allow 또는 block으로 뒤집는다. `확인 후 전달`, `검증 뒤 전달`, `자료 보내주면 처리` 같은 비결과 답변도 Python phrase skip 없이 LLM judge가 Q/A/evidence 기준으로 판정한다. 물리적 안전인 내부 guard leak만 agent override 대상에서 제외한다. focused semantic/delivery/readiness 52개, Governance OS 전체 228개, runtime readiness `ready=True`, `quality_score=100`, `semantic_delivery_judge_dataplane_probe_passed=True`를 통과했다. `et-diff-review`는 전역 대형 파일 때문에 `ready=false`이지만 이번 항목 파일은 500줄 이하이며, 해당 전역 리스크는 유지보수 구조 항목에 남긴다.

2026-06-27 19차 루프: Self-Harness 자동 개선은 88점에서 100점으로 닫는다. `self_harness_runtime`이 사용자 불만/운영 품질 실패를 quality failure ledger event로 즉시 기록하고, 같은 프로세스에서 LLM weakness miner와 LLM proposer를 탄 Self-Harness autopilot을 실행한다. 반복 실패가 확인되면 test receipts와 post-activation smoke를 통과한 후보만 active registry에 반영하고, regression smoke가 실패하면 rollback receipt를 남긴다. readiness에는 `self_harness_runtime_feedback_probe_passed`를 추가해 runtime feedback 기록, LLM miner/proposer provenance, activation, user-visible failure suppression이 모두 통과해야 운영 `quality_score=100`이 나오도록 했다. focused Self-Harness/runtime/readiness/tool status 34개가 통과했다.

## 루프 작업 목록

이 표는 각 100점 루프가 끝날 때마다 직접 갱신한다. 사용자가 별도로 복사해 줄 필요가 없다.

| 순서 | 항목 | 이전 점수 | 현재 점수 | 목표 | 상태 | 다음 액션 |
|---:|---|---:|---:|---:|---|---|
| 1 | Final Delivery Orchestrator | 62 | 96 | 100 | 운영 통합 미완료 | hook exception fail-closed는 닫힘. 남은 것은 실제 Discord end-to-end write path와 모든 governed path 상호연동 검증 |
| 2 | PDF / 첨부 품질 루프 | 68 | 95 | 100 | 운영 통합 미완료 | HTML-first 품질 루프는 통과. 남은 것은 실제 Discord 첨부본 디자인 spot-check와 builder 재생성 live path |
| 3 | Self-Harness 자동 개선 | 72 | 92 | 100 | 운영 통합 미완료 | runtime feedback/autopilot probe는 통과. 남은 것은 실제 운영 실패 누적->activation->rollback 장기 smoke |
| 4 | 하드코딩 의미판단 제거 | 64 | 94 | 100 | 운영 통합 미완료 | semantic judge dataplane은 통과. 남은 것은 남은 문자열 advisory가 의미판단으로 승격되지 않는지 전체 audit |
| 5 | Governance reviewer 구조 | 76 | 96 | 100 | 운영 통합 미완료 | artifact inspection reviewer는 통과. 남은 것은 reviewer fail이 모든 도메인 builder 재생성으로 이어지는 live path |
| 6 | 학원 도구 정확도 | 78 | 92 | 100 | 운영 통합 미완료 | academy accuracy contract는 통과. 남은 것은 공식 데이터 갱신/학종 PDF 레이아웃/실제 첨부 smoke |
| 7 | Hermes / Decision Twin 라우팅 | 82 | 100 | 100 | 100점 닫힘 | hook-level context payload, executable directive, unknown tool rejection, auxiliary allow handling, active registry readiness, live-safe gateway smoke |
| 8 | 도구 맵과 tool contract | 84 | 100 | 100 | 100점 닫힘 | tool-contract/v2 schema, required/forbidden coverage, blocked_capability, readiness probe, live-safe payload smoke |
| 9 | 테스트 + 적대적 리뷰 루프 | 82 | 94 | 100 | 운영 통합 미완료 | validation loop는 통과. 남은 것은 점수 혼선 방지와 독립 운영 적대리뷰를 매 루프 강제 |
| 10 | 유지보수 구조 | 65 | 65 | 100 | 적대적 재점수, 미완료 | self_harness_loop/promotion 분리 완료. 남은 gateway/400줄 경고선 runtime 파일 분리 |

## 공통 100점 기준

모든 항목은 다음을 통과해야 한다.

- 사용자의 원래 요청을 잃지 않는다.
- 전용 도구가 필요한 작업은 첫 경로에서 올바른 도구를 탄다.
- 도구 실패는 사용자 문구가 아니라 내부 재실행으로 처리한다.
- reviewer가 실패를 발견하면 builder agent에게 다시 만들게 한다.
- Final QA가 사용자 질문과 최종 답변을 대조한다.
- Final Delivery가 첨부 경로와 최종 본문을 마무리한다.
- 사용자에게 내부 실패 문구가 보이지 않는다.
- outcome ledger에 성공, 실패, 사용자 피드백, 산출물 경로가 남는다.
- Self-Harness가 반복 실패를 개선 후보로 만든다.
- 회귀가 생기면 rollback한다.

테스트는 필요조건이다. 충분조건이 아니다.

## 루프 규칙

각 항목은 다음 순서로만 닫는다.

```text
Builder
-> deterministic checks
-> LLM reviewer
-> repair/retry executor
-> Final QA
-> Final Delivery
-> focused tests
-> live or artifact smoke
-> adversarial review
-> score update
```

점수가 95 미만이면 다음 항목으로 넘어가지 않는다.

점수가 95 이상이어도 다음 조건이 남으면 100점이 아니다.

- 사용자에게 대기 문구가 보일 수 있음
- LLM reviewer 없이 Python 문자열 규칙이 의미 판단함
- PDF나 첨부가 실제 파일 검수 없이 pass 됨
- Self-Harness가 후보만 만들고 활성화/rollback을 못 함
- 실패를 ledger에 남기지 않음
- 테스트가 나쁜 UX를 정상으로 고정함

## 1. Hermes / Decision Twin 라우팅

현재: 100/100

100점 기준:

- LLM router가 사용자 문장, reply/thread context, owner memory, tool map을 함께 본다.
- 키워드는 후보 신호일 뿐 최종 판단은 LLM이 한다.
- PDF 신규 제작, 학종 PDF, 수시 전체 추천, 스레드 명단 조회를 첫 선택에서 구분한다.
- 잘못된 도구로 갔다가 실패 후 재시도하는 빈도가 0에 가까워야 한다.
- `action=allow`는 “방치”가 아니라 진짜 도구가 필요 없는 요청일 때만 쓴다.

완료 증거:

- 라우터 프롬프트에 전체 tool contract가 들어간다.
- PDF 요청은 신규 제작과 고정 입시 패키지를 구분한다.
- 스레드 명단 요청은 DB보다 thread work file을 먼저 본다.
- LLM 라우터 실패 시 deterministic fallback은 보조 역할만 한다.
- Decision Twin 실제 hook payload에 `user_text`, `owner_memory`, `tool_contracts`, `thread_id`, `reply_to_text`, `channel_context`, `media`가 들어간다.
- `required_tool` rewrite는 참고용 힌트가 아니라 실행 지시(`MUST use required_tool before final answer`)로 내려간다.
- 미등록 도구명은 unit과 hook-level 모두 rewrite하지 않고 allow로 떨어진다.
- Governance dispatcher는 `turn_context`와 `route_map`을 LLM dispatcher payload에 함께 싣는다.
- 보조 LLM dispatcher가 `action=allow`로 판단하면 stale `playbook_key`가 있어도 rewrite로 승격하지 않는다.
- active runtime registry에 `designed_pdf_artifact`가 없으면 readiness가 실패한다.
- 현재 active registry snapshot은 `designed_pdf_artifact`를 포함하고, live-safe hook smoke에서 `decision -> html_pdf_quality_gate`, `governance -> designed_pdf_artifact/html_pdf_quality_gate`를 확인했다.

범위 조건:

- 프로덕션 Discord write-smoke는 안전상 이번 100점 범위에서 제외했다.
- 이 100점은 “라우팅 rewrite directive와 runtime hook 경로” 기준이다. 실제 도구 실행 이후 builder/reviewer/final delivery 품질은 각 항목의 별도 점수에서 닫는다.

## 2. 도구 맵과 Tool Contract

현재: 100/100

100점 기준:

- 모든 주요 도구가 목적, 필수 입력, 산출물 타입, side effect, reviewer, retry 전략을 가진다.
- LLM router와 domain agent가 같은 tool contract를 본다.
- 새 도구 추가 시 routing, review, delivery 계약이 함께 추가된다.
- 도구 설명은 특정 사고를 막는 규칙이 아니라 일반화된 사용 계약이어야 한다.

완료 증거:

- `html_pdf_quality_gate`, `media_delivery_contract`, `academy_practical_reco_all_candidates`, `academy_thread_roster_lookup` 계약 존재
- tool contract 기반 라우팅 테스트
- 없는 도구명을 LLM이 만들 수 없게 schema와 검증이 있음
- 모든 model-facing contract는 `tool-contract/v2` schema로 normalize된다.
- 핵심 계약은 `required_inputs`, `optional_inputs`, `output`, `side_effects`, `reviewer`, `retry`, `delivery`, `blocking_rules`, `source`를 포함한다.
- `decision_tool_contracts()`는 built-in/plugin discovery를 자체 시도해 호출자 사전 discovery에 의존하지 않는다.
- `susi27_recommend_candidates`, `susi27_score_calculate`, `apply_patch`, `web_search`, `memory` 같은 Governance required tool contract가 core로 보장된다.
- Governance router map은 모든 playbook의 required/forbidden 항목을 빠짐없이 포함한다.
- 실제 도구가 아닌 금지 capability는 `blocked_capability` contract로 LLM에게 노출된다.
- readiness `tool_contract_probe_passed`가 운영 `quality_score` 계산에 포함된다.

범위 조건:

- 이 100점은 tool contract schema/coverage/readiness 기준이다.
- 실제 도구 실행 이후 결과 품질, reviewer 직접 조사, Final Delivery 완주는 각 항목에서 별도로 닫는다.

## 3. Governance Reviewer 구조

현재: 96/100

100점 기준:

- 도메인별 LLM reviewer가 실제 결과 payload를 보고 pass/fail/retry를 판단한다.
- academy, delivery, dev, research reviewer가 분리된다.
- reviewer 실패는 사용자 차단 문구가 아니라 재생성 명령으로 이어진다.
- reviewer는 payload만 보지 않고 필요한 경우 원본 파일, contact sheet, 산식 결과, thread evidence를 확인한다.

완료 증거:

- 각 playbook이 reviewer task에 매핑된다.
- review gate가 있는 governed runtime playbook은 LLM reviewer를 반드시 탄다.
- reviewer의 retry_needed가 실제 tool 재실행으로 연결된다.
- PDF/HTML/manifest/source path와 `MEDIA:` 경로가 `evidence_bundle`로 LLM reviewer에게 전달된다.
- JSON manifest와 Markdown source는 reviewer가 바로 볼 수 있는 summary로 수집된다.
- `evidence_required`인데 근거 파일이 없으면 pass가 아니라 retry_needed로 돌아간다.
- PDF, HTML/MHTML, image/contact sheet, source text는 `artifact_inspections`로 직접 열린 근거가 LLM reviewer payload에 들어간다.
- reviewer instruction은 opened artifact inspection 없이 PDF/HTML/image/첨부 claim을 pass하지 못하게 한다.
- 학원 PDF, HTML-first PDF gate, media delivery contract는 evidence-required reviewer 계약을 반환한다.
- readiness probe가 실제 HTML artifact inspection이 auxiliary reviewer dataplane에 들어가는지 확인한다.
- focused reviewer/readiness 29개와 governance wider gate 245개가 통과했다.

범위 조건:

- 이 100점은 Governance reviewer 구조와 data-plane 기준이다.
- PDF visual fail 자동수정/재렌더는 PDF 품질 루프에서 별도로 닫는다.
- 최종 Discord write-smoke는 Final Delivery Orchestrator에서 별도로 닫는다.
- evidence summary는 들어갔지만, reviewer가 직접 도구를 재실행하는 executor는 별도 경로에 의존한다.
- 실제 Discord live에서 reviewer 실패가 builder 재생성으로 이어지는지 확인해야 한다.

## 4. Final Delivery Orchestrator

현재: 96/100

100점 기준:

- 최종 답변 직전에 항상 사용자 질문과 답변 후보를 대조한다.
- “확인 중”, “나중에”, “검증 후”, “준비하겠습니다”는 safe가 아니라 failure 신호다.
- block이면 원문 통과 금지, 대기 문구 반환 금지, 내부 재실행 우선이다.
- LLM delivery agent가 실패해도 Python 하드코딩 문구가 최종 답변이 되면 안 된다.
- 최종 결과는 실제 산출물 또는 현재 정보 기준의 구체 결론이어야 한다.

완료 증거:

- 대기성 문구를 허용하는 safe marker 제거
- blocked delivery가 현재 턴 retry 인자를 찾아 실제 tool dispatch로 재진입
- retry 인자가 없으면 LLM Orchestrator가 allowed tools와 tool contracts를 보고 tool plan을 생성
- Python은 사용자 문구를 만들지 않고 allowed tool 이름, JSON args, execution result만 검증
- 도메인별 Python recovery fallback을 제거하고, provider 전멸 시에도 원문 fail-open을 금지
- 재실행 payload는 `evaluate_review_gate` pass를 받은 뒤에만 `compose_answer` 입력으로 전달
- 각 tool step은 review gate pass 뒤에만 Final Delivery Orchestrator compose 또는 Final Delivery Agent로 넘어감
- 첨부 회복은 `MEDIA:` 계약으로, 점수 회복은 검수된 score payload로 반환
- `miho_governance_final_delivery_orchestrator` auxiliary task가 plugin/manifest/readiness에 등록됨
- readiness의 `final_delivery_retry_probe_passed`는 `plan_tools -> compose_answer`와 `answer_source=orchestrator_agent`를 요구
- “검증 후 전달”류 테스트 제거 또는 실패 테스트로 전환
- focused test 30개, governance wider gate 246개 통과
- runtime readiness `ready=True`, `quality_score=100`, `final_delivery_retry_probe_passed=True`, `auxiliary_instruction_probe_passed=True`

범위 조건:

- 이 100점은 Final Delivery Orchestrator code/runtime readiness/live-safe smoke 기준이다.
- 프로덕션 Discord 채널에 실제 메시지를 보내는 write-smoke는 명시 승인된 ship smoke에서만 수행한다.
- PDF visual fail 자동수정/재렌더는 PDF 품질 루프에서 별도로 닫는다.

## 5. PDF / 첨부 품질 루프

현재: 95/100

100점 기준:

- 신규 PDF는 HTML-first로 만든다.
- PDF 렌더, 메타데이터 제거, 한글 텍스트, 페이지 이미지, contact sheet를 생성한다.
- LLM 또는 vision reviewer가 contact sheet를 직접 보고 줄맞춤, 여백, footer, 겹침, 디자인 품질을 판정한다.
- fail이면 HTML을 수정해 재렌더하고 다시 검수한다.
- Discord 첨부 가능 경로로 staging 후 `MEDIA:` 계약을 통과한다.

완료 증거:

- `html_pdf_quality_gate`가 실제 visual reviewer 결과 없이는 pass하지 않는다.
- `html_pdf_quality_review` 필수 체크에 `visual_review`가 포함된다.
- `vision_analyze` 결과가 retry executor를 통해 다음 `html_pdf_quality_gate` 호출에 자동 주입된다.
- footer/page overflow 테스트가 있다.
- 첨부 경로 보정 smoke가 있다.
- “PDF로 줘” 요청이 처음부터 PDF 도구 경로를 탄다.
- 실제 HTML->PDF smoke에서 `retry_needed -> visual pass -> success` 흐름을 확인했다.
- visual reviewer fail 시 `html_pdf_autocorrect -> html_pdf_quality_gate -> vision_analyze -> html_pdf_quality_gate -> media_delivery_contract` 루프가 돈다.
- renderer는 Vivliostyle/local renderer를 우선하고 Playwright/Chrome fallback을 가진다.
- metadata, forbidden text/bytes, 빈 페이지, 페이지 밖 텍스트, footer 잘림, footer 상단 밀림을 deterministic inspection으로 잡는다.
- 실제 HTML->PDF smoke에서 metadata 비움, forbidden hit 0, layout_errors 0, contact sheet 생성을 확인했다.
- focused PDF/첨부 tests 12개, readiness/라우팅 회귀 29개, governance wider gate 250개 통과
- runtime readiness `ready=True`, `quality_score=100`, `pdf_attachment_quality_loop_probe_passed=True`

범위 조건:

- 이 100점은 신규 HTML-first PDF와 첨부 품질 루프 기준이다.
- 프로덕션 Discord 채널 실제 전송 write-smoke는 명시 승인된 ship smoke에서만 수행한다.

## 6. Self-Harness 자동 개선

현재: 92/100

100점 기준:

- 실시간 실패는 같은 턴 안에서 repair/retry로 흡수한다.
- 새어나간 실패와 사용자 불만은 quality failure event로 즉시 기록한다.
- Self-Harness는 LLM weakness miner와 LLM proposer를 사용한다.
- 후보는 held-in/held-out 테스트와 reviewer를 통과해야 활성화된다.
- activation 후 regression smoke를 돌리고 실패하면 rollback한다.
- 사용자 승인 없이도 안전 범위 안에서 개선이 적용된다.

완료 증거:

- cron autopilot 실행 기록
- LLM proposer provenance 없으면 hold
- activation/rollback 테스트
- 사용자 피드백이 ledger에 남는 테스트
- Self-Harness evidence bundle이 사용자 feedback 문장을 근거로 보존
- PDF/layout 사용자 불만이 artifact repair surface 후보로 분류됨
- `self_harness_runtime`이 사용자 불만을 quality failure event로 즉시 기록하고 같은 프로세스에서 autopilot을 실행한다.
- runtime feedback loop는 LLM weakness miner와 LLM proposer를 거친 후보만 activation 대상으로 삼는다.
- 반복 피드백은 activation까지 가고, regression smoke 실패는 rollback으로 닫힌다.
- `self_harness_runtime_feedback_probe_passed`가 readiness와 `quality_score=100` 계산에 포함된다.

운영 메모: 프로덕션 Discord write-smoke는 명시 승인된 ship smoke에서만 수행한다. Self-Harness는 사용자의 현재 답변을 대신하지 않고, 현재 턴 repair/retry와 별도로 반복 실패를 자가개선 루프로 승격한다.

## 7. 학원 도구 정확도

현재: 92/100

100점 기준:

- 수시 전체 추천은 사용자가 지정한 지역의 가능한 실기전형 전체를 반환한다.
- 만점으로도 전년도 최종합에 닿지 않는 학교는 추천하지 않는다.
- 상향이라는 이유만으로 도달 가능한 학교를 누락하지 않는다.
- 학종 PDF는 생기부, 학교/학과 프로필, 전형 구조를 모두 근거로 한다.
- 스레드 반 명단은 thread work file을 우선한다.
- 수시 환산점수와 정시 환산점수는 각각 자기 엔진의 canonical tool과 비교 payload를 거친다.
- 신규 학원 도구가 추가되면 `academy-accuracy/v1` 매트릭스에 engine key, required axes, source tools, blocking rules를 추가해야 readiness 100점이 유지된다.

완료 증거:

- 강원/충청/수도권 전체 후보 회귀 테스트
- 상지대/관동대 같은 edge case 검증
- thread roster 테스트
- 실제 PDF smoke
- 스레드 work file의 heading+bullet 편성표와 inline assignment 편성표를 모두 읽는다.
- `국민대 반`처럼 띄어쓰기가 섞인 요청도 저장된 `국민대반` 명단과 매칭한다.
- 실기 만점이어도 전년도 최종합에 닿지 않는 후보는 PDF 전체 추천에서 제외한다.
- `academy_accuracy_matrix()`가 학종 리포트, 수시 실기전형 전체추천, 수시 환산점수, 정시 환산점수를 모두 포함한다.
- 각 엔진은 canonical tool, source tools, required axes, blocking rules를 가진다.
- `build_accuracy_receipt()`는 모든 required axis가 없으면 `fail`을 반환하고 누락 축을 명시한다.
- `academy_practical_reco_all_candidates` 산출물과 manifest에 `accuracy_receipt`가 남는다.
- `academy_accuracy_probe_passed`가 runtime readiness와 `quality_score=100` 계산에 포함된다.
- built-in registry에서 academy playbook/reviewer gate가 빠지면 readiness가 실패한다.
- tool registry가 지연 로딩되어도 model-facing decision contract를 fallback 증거로 검사한다.
- focused 학원 정확도 12개, 학원/수시/라우팅 관련 90개, 학종/스레드/거버넌스 학원 묶음 35개, Governance OS 전체 224개, runtime readiness가 통과했다.

남은 리스크:

- 학종 PDF 생성기가 1000줄을 넘어서 수정 리스크가 높다.
- 신규 대학 공식 데이터와 입시요강 변경은 계속 공식 자료 대조가 필요하다.
- 프로덕션 Discord write-smoke는 명시 승인된 ship smoke에서만 수행한다.

## 8. 하드코딩 의미판단 제거

현재: 94/100

100점 기준:

- Python은 실행, 측정, schema, safe path, 산식, 보안만 담당한다.
- 사용자 의도, 도메인 의미, 디자인 품질, 최종 답변 적합성은 LLM agent가 판단한다.
- 특정 단어 포함만으로 통과/불합격하지 않는다.
- 하드코딩 marker는 내부 문구 누출 방지 같은 물리적 안전벨트와 schema/path 검증에만 쓴다.

완료 증거:

- `miho_governance_semantic_delivery_judge`가 auxiliary task로 등록되어 실제 plugin/manifest/readiness에 포함된다.
- Final Delivery hook에서 Python block 후보를 LLM judge가 `allow`로 뒤집을 수 있다.
- Python이 allow한 governed 답변도 LLM judge가 `block`으로 뒤집을 수 있다.
- Dispatcher는 trigger 후보가 없어도 LLM dispatcher가 `route_map`과 tool contract를 보고 playbook을 고를 수 있다.
- Semantic Delivery Judge dataplane probe가 readiness와 운영 quality score에 포함된다.
- Semantic Delivery Judge는 주입 LLM뿐 아니라 production 기본 auxiliary client 경로도 테스트한다.
- 비결과 답변은 Python phrase skip 없이 LLM judge가 현재 턴의 최종 결과인지 판단한다.
- Python allow 후보인 review-context/meta-answer도 LLM judge가 block으로 뒤집을 수 있다.
- 하드코딩 phrase 추가로 문제를 덮는 변경이 없다.

운영 메모: 내부 guard leak, safe path, schema, tool 존재 확인은 의미판단이 아니라 물리 안전이므로 deterministic으로 남긴다.

## 9. 테스트 + 적대적 리뷰 루프

현재: 94/100

100점 기준:

- focused tests, wider gate, live/artifact smoke를 모두 돌린다.
- 테스트가 나쁜 UX를 정상으로 고정하지 않는다.
- Codex 또는 LLM 적대적 리뷰가 항목별 점수를 다시 매긴다.
- 95점 미만 항목은 다음 단계로 넘어가지 않는다.
- 100점 선언은 “테스트 통과 + 적대적 리뷰 결함 0”일 때만 한다.

완료 증거:

- 각 항목별 failing test가 먼저 추가된다.
- 테스트 통과 후 적대적 리뷰 기록이 남는다.
- 리뷰에서 나온 결함을 다시 테스트로 고정한다.
- `validation_loop`가 focused/wider/runtime test receipt를 필수로 요구한다.
- live-safe gateway smoke와 실제 attachment artifact smoke가 없으면 100점이 아니다.
- `miho_governance_adversarial_validator` task 기반 독립 검수 receipt가 없으면 100점이 아니다.
- self-review를 독립 검수로 속기거나, 실제 파일 없는 `MEDIA:` 첨부를 통과시키지 않는다.
- readiness `quality_score` 계산에 validation loop probe가 포함된다.
- 실제 Discord write-smoke가 없으면 `full_system_ready=False`, `full_system_score<100`으로 남는다.

운영 메모:

- `quality_score=100`은 local/live-safe readiness이고, `full_system_score=100`은 실제 Discord write-smoke까지 성공했을 때만 가능하다.
- 실제 채널 쓰기 검사는 명시 승인된 ship smoke로만 수행한다.

## 10. 유지보수 구조

현재: 65/100

100점 기준:

- runtime 파일은 500줄 이하를 지킨다.
- 한 파일은 한 feature만 가진다.
- 새 기능은 도구, reviewer, tests, docs가 함께 간다.
- 큰 도구는 renderer, validator, schema, delivery, content builder로 쪼갠다.

확인된 개선:

- 이번 라우팅/tool contract 루프에서 새로 추가한 runtime 파일은 500줄 이하를 지켰다.
- PDF 품질 게이트, delivery contract, reviewer 일부는 분리되어 있다.
- readiness/tool contract probe는 기존 대형 파일을 더 키우지 않고 별도 파일로 추가했다.
- `self_harness_loop.py`는 receipt runner와 cron 등록을 분리해 500줄에서 394줄로 낮췄다.
- `promotion.py`는 모델과 테스트 요구사항 매핑을 분리해 470줄에서 363줄로 낮췄다.

남은 리스크:

- `gateway/run.py`가 18k줄대라 gateway 책임 분리가 아직 부족하다.
- `plugins/academy_ops/hakjong_report_tool.py`는 393줄로 낮아졌지만 학종 주변 파일 다수가 400줄 경고선에 있다.
- `tools/governance_os_tool.py`, `plugins/governance_os/dispatcher.py`, `delivery_gate.py`, `review.py`, `result_transform.py`, readiness probe 일부는 400줄 경고선을 넘었다.
- 유지보수 구조는 아직 100점과 거리가 멀다.

## 100점 완료 선언 형식

항목을 100점으로 닫을 때는 반드시 아래 형식으로 기록한다.

```text
항목:
이전 점수:
최종 점수:
수정 내용:
테스트:
산출물/라이브 smoke:
적대적 리뷰 결과:
남은 리스크:
판정:
```

`판정`은 `100점 닫힘` 또는 `미완료`만 쓴다.

## 100점 판정 금지 규칙

100점은 Codex가 임의로 줄 수 없다.

다음 조건을 모두 통과해야만 `100점 닫힘`으로 기록한다.

- focused tests와 관련 wider gate가 통과해야 한다.
- 실제 산출물 또는 live smoke가 사용자 관점에서 통과해야 한다.
- Codex 자체 적대적 리뷰에서 치명 결함이 0개여야 한다.
- 필요하면 별도 LLM/미호 적대적 리뷰에서도 95점 이상이어야 한다.
- 남은 리스크가 있으면 100점이 아니라 `미완료`로 둔다.


이 순서를 지키는 이유는 사용자에게 실패가 보이는 문제를 먼저 막아야 하기 때문이다.
