# MihoLifeRecordVision — Design (life_record vision 재설계)

## 아키텍처 변경 (정규식 → vision + 합의 + 중앙승격)

```
ingest_life_record(pdf, bundle_dir):
  1. render_page_images(pdf, zoom=3.0)        # pdf_reader.py 확장 (PyMuPDF get_pixmap)
  2. vision_extract × N(<=3)                  # vision_extractor.py (gpt-5.5, 주입형 resolver)
  3. consensus(N results)                     # consensus.py — 항목별 합의
       - 합의 → confidence=0.99, review_status=confirmed
       - 불일치 → 해당 항목 크롭 재확인 1회 → 그래도 불일치 → needs_review
  4. save_import(...)                          # repository.py — review_status/confidence 합의 반영
  5. run_verification(...)                     # verifier.py — 합의/누락 기반
  6. if 모든 항목 confirmed → promote_to_central()  # repository.py 신설 (중앙 학생DB)
```

## 모듈 인터페이스

### vision_extractor.py (신설)
- `VisionResolver = Callable[[list[str], str], Awaitable[str]]` (이미지 data-url 리스트 + 프롬프트 → JSON). 기본 = codex gpt-5.5. **주입형**(테스트는 fake).
- `extract_life_record(images, *, resolver) -> dict` — 구조화 JSON: `{identity, attendance[], grades[], notes[], awards[]}`. 스키마 강제.
- 개인정보: 주민번호는 birth_masked(앞6+마스킹)만, 뒷자리 저장 금지.

### consensus.py (신설)
- `reconcile(results: list[dict], *, max_rounds=3) -> dict` — 항목별 다수결/일치. `{field: {value, agreed, confidence}}`.
- `needs_recheck_fields(reconciled) -> list` — 불일치 필드.
- 무한루프 금지: 최대 max_rounds 후 불일치는 needs_review 확정.

### pdf_reader.py (확장)
- `render_page_images(pdf_path, *, zoom=3.0, pages=None) -> list[bytes]` (PNG). 기존 extract_pdf/photo 유지.

### repository.py (확장)
- `central_db_path() -> Path` = `MIHO_HOME/life_records/central.sqlite3`
- `promote_to_central(bundle_db, document_id)` — 확정본을 중앙DB 학생 단위 upsert, 학기 누적.
- `lookup_central(query)` — 중앙DB 학생 조회.
- `confirm_rows(...)` — needs_review→confirmed.

### tools.py / __init__.py
- 기존 5도구 유지. `life_record_lookup`(중앙DB), `life_record_confirm`(사람 확정) 추가.

## 스키마 변경
- subject_grades/notes: + UNIQUE(student_document_id, grade, semester, subject) (학기 누적)
- 중앙DB CENTRAL_SCHEMA: students + central_grades/notes/attendance/awards (UNIQUE student+grade+semester+subject)
- extraction_method: "codex_vision_gpt5.5_v1"

## Wiring Map
- ingest_pdf_tool → service.ingest_life_record → vision_extractor(codex) → consensus → repository.save_import → verifier → promote_to_central
- lookup_tool → repository.lookup_central
- confirm_tool → repository.confirm_rows → promote_to_central 재시도

## 테스트 시나리오 (T-ID)

| T-ID | 시나리오 | 방식 |
|------|----------|------|
| T-01 | render_page_images: PDF→PNG bytes 리스트, zoom 반영 | 단위 (실제 PDF) |
| T-02 | vision_extractor: fake resolver JSON → 구조화 dict 정규화 | 단위 (fake) |
| T-03 | consensus: 3결과 중 2일치 → agreed=True/confirmed | 단위 |
| T-04 | consensus: 전부 불일치 → needs_review, 최대 3회 종료(무한X) | 단위 |
| T-05 | 학기 누적: 1학년 doc 후 2·3학년 doc → grades 누적 | 단위 (DB) |
| T-06 | 학생 동일성: 같은 이름+학교+생년 재투입 → student 1개 유지 | 단위 (DB) |
| T-07 | promote_to_central: 전부 confirmed → 중앙DB 학생 단위 저장 | 단위 (DB) |
| T-08 | lookup_central: 중앙DB 학생 조회 반환 | 단위 (DB) |
| T-09 | 개인정보 마스킹: birth_masked만 저장, 뒷자리 미저장 | 단위 |
| T-10 | 기존 5도구 + 신규 2도구 등록 | 단위 (register) |
| T-11 | needs_review confirm → confirmed + 중앙 승격 | 단위 (DB) |
| T-12 | [LIVE,opt-in] 실제 샘플 2개 vision 추출 LLM 채점 | 통합 (MIHO_LIFE_RECORD_LIVE_TEST=1) |

## 합의/검증 정책
- 합의된 항목만 confirmed. 불일치/저신뢰는 needs_review.
- 100% = 전 항목 합의 or 사람 확정 (무한루프 없음).
- vision 비용: N=2 기본 + 불일치 시 1회 추가(최대 3).
