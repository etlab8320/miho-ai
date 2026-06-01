# miho-ai — Layer8 Final Report
Generated: 2026-06-01 03:32:28

## Phase History
| Phase | Verdict | Coverage | Timestamp | Hash |
|-------|---------|----------|-----------|------|
| plan | Pass | 90% | 2026-06-01 02:41:58 | LOCAL |
| design | Pass | 88% | 2026-06-01 02:44:07 | LOCAL |
| do | Pass | 92% | 2026-06-01 03:30:47 | LOCAL |
| check | Pass | 90% | 2026-06-01 03:32:28 | LOCAL |

## Remaining Risks
Updated 2026-06-01 after codex review (82/100) follow-up fixes.

Resolved this round:
- P1 인증 전 생기부 자동수집 → `_capture_gateway_context`에 PII 인증 게이트(fail-safe) 추가.
- P1 미상 학생 중앙DB 승격 → `all_confirmed` 필수신원(이름·학교·생년월일) 검증 + `promote_to_central` 2차 가드.
- P1 `uv lock --check` → lock이 pyproject와 일치(통과). 커밋 정리만 남음.
- P2 재수집 시 문서 헤더 stale → `_upsert_document` UPSERT.
- P2 대형 PDF 메모리/시간 폭발 → 페이지 cap(MAX_PAGES=50) + 배치 세마포어(MAX_CONCURRENT_BATCHES=3).
- P2 삭제 경로 confinement → `delete_bundle`이 MIHO_HOME/life_records 밖 거부.
- 프론트 진짜 버그 → `no-useless-escape`(4) + render 중 ref 쓰기(1) 수정.

Open (방향 결정 필요):
- 프론트 린트 21건: react-hooks 신규 엄격룰(set-state-in-effect 12 등) + react-refresh dev룰 3. 전면 effect 리팩 vs error→warn 완화 결정 필요. 빌드는 통과.
- P2 프론트 에러 UX(api.ts 원시 에러 노출): i18n 친화 메시지 매핑 — 다국어 통합 작업이라 별도.
- e2e/runtime smoke: playwright 설정 부재로 미실행.

## Rollback Points
- `layer8/miho-ai/pre-design`
- `layer8/miho-ai/pre-do`
- `layer8/miho-ai/pre-plan`
