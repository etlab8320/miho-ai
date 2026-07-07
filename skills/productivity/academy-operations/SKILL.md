---
name: academy-operations
description: "Operate academy-management workflows for 맥스체대입시: PACA/Peak student, attendance, payment, record, and Discord-facing operations."
version: 1.0.0
author: Miho Agent
license: MIT
platforms: [macos]
metadata:
  miho:
    tags: [academy, paca, peak, attendance, student-management, discord]
    related_skills: [miho-agent]
---

# Academy Operations

Use this skill when 맥스 asks for academy-management data or actions such as 학생관리, 출석 명단, 결석자, 지각자, 학생 검색, 상담 후보, 미납, Peak 기록, 반배치, or PACA/Peak Discord operations.

## Operating principle

Do not invent student or attendance data. These workflows affect real students and parent communication, so answer only from live PACA/Peak data, pasted user data, or clearly labeled assumptions.

For read-only requests, act immediately when the intent is obvious:

- “오늘 출석 명단” → fetch today's Peak attendance.
- “결석자만” → fetch today's Peak attendance and filter absent.
- “지각자만” → fetch today's Peak attendance and filter late.
- **“오늘 출석해야 할 학생들 / 오늘 출석할 학생 명단” → use `academy_class_roster_range` for today's date, not `academy_attendance_day`.** Attendance counts can be zero before check-in even when a class roster exists. See `references/attendance-roster-routing.md`.
- **“이번주 수요일 출석해야 할 학생 명단” / other weekday-specific roster asks** → resolve the weekday into an explicit `YYYY-MM-DD` first, then call `academy_class_roster_range` with `start_date == end_date == resolved date` and `with_roster=true`. If the user asked for an image, set `image=true` so the roster renderer returns a single MEDIA attachment. Do **not** route these through `academy_attendance_day`. See `references/weekly-roster-routing-note.md` and `references/attendance-relative-date-image.md`.
- “오늘 제자리멀리뛰기 기록” / “오늘 ○○ 기록” → fetch today's Peak records and aggregate by event; if there is no dedicated leaderboard endpoint, fan out over active Peak students and collect `/peak/records`.
- “학생 찾아줘/상세” → search PACA, then summarize only returned fields.
- “학생카드 줘/카드좀줘봐” with a name in the message → generate and return the API-backed student-card image immediately; do not ask for the name again.

For writes such as 출석 처리, 결제 완료, 기록 입력, or batch updates, stop for explicit confirmation unless a verified confirmation/audit flow is already present.

## Student-card image retrieval

When the Discord-facing `academy_student_card_image` / `academy_student_summary` wrappers fail to pick up a name that was present in the user message, do not stop with the wrapper's “학생 이름이나 검색어를 알려줘” response. Treat that as an argument propagation issue and call the underlying read-only path with `student_query` explicitly, or use the stored PACA binding directly:

See `references/consultation-note-save.md` for the paired consultation-note save workaround and verified local-db pattern.

## Uploaded 생기부 PDF 저장

When the user uploads a `학교생활세부사항기록부(학교생활기록부II)` PDF and says “db에 저장해놔”, treat it as a **life-record document import**, not a 상담 메모 write.

1. Prefer the `plugins.life_record` pipeline / repository for the document store.
2. Save the original PDF into the thread-scoped `life_records.sqlite3` bundle (or the current life-record bundle for the thread).
3. Populate the identity from the document itself: 학생명, 학교명, 학년, 반, 번호, and 문서일자 when visible.
4. If PACA enrichment or account lookup fails but the PDF identity is readable, still persist the document locally and verify by reading back the inserted row.
5. If the user says “아까껀 지우고/이전 건 지우고”, remove the previous active `life_record/*` bundle for that thread before saving the new PDF. If you quarantine first for safety, permanently delete or clearly report that it was archived rather than deleted.
6. For scanned/image PDFs where text extraction returns empty, render the first page to PNG and use vision to extract identity, then do an identity-only `save_import` while preserving the original PDF. Do not fail just because embedded text is absent.
7. Final reply should be short and factual: previous active save removed, DB path, document id, student, school, page count, and archived PDF path.

See `references/life-record-pdf-save.md` for the verified save pattern and the local DB read-back check. See `references/life-record-replace-scanned-pdf.md` for the scanned-PDF replacement workflow and verification query.


```python
from plugins.academy_ops.auth_store import load_bindings, decrypt_token
from plugins.academy_ops.academy_api import AcademyApiClient
from plugins.academy_ops.student_card import AcademyStudentCardService
from plugins.academy_ops.student_card_renderer import StudentCardImageRenderer

binding = next(iter(load_bindings().values()))
token = decrypt_token(binding.token_ciphertext) or ""
client = AcademyApiClient(token=token)
card = AcademyStudentCardService(client).build("학생명")
image_path = StudentCardImageRenderer().render(card)
```

Return `MEDIA:<image_path>` plus a concise Korean summary from `card.to_public_dict()`. Keep sensitive fields out of the reply.

## PACA/Peak Discord binding check

When running inside the local Miho project, PACA/Peak Discord login bindings are stored under `~/.miho/academy_ops/` by the `plugins.academy_ops` package.

Before saying an account is unlinked, verify the binding store:

```python
from plugins.academy_ops.auth_store import load_bindings, decrypt_token
bindings = load_bindings()
```

A binding confirms the Discord user is linked, but not necessarily that a specific operation tool is wired into the agent loop. If a tool wrapper fails, fall back to a direct read-only API probe with the stored token rather than telling the user the integration is absent.

## Read-only workout-plan retrieval

For requests like “어제 박성준 운동계획서”, “강사 운동계획”, or “수업계획 보여줘”, use the live Peak plans endpoint before saying the operation is unsupported. Resolve relative dates with the system date, then query by `date`:

```python
import httpx
from plugins.academy_ops.auth_store import load_bindings, decrypt_token
from plugins.academy_ops.paca_config import resolve_paca_base_url

binding = next(iter(load_bindings().values()))
token = decrypt_token(binding.token_ciphertext)
base = resolve_paca_base_url()
response = httpx.get(
    f"{base}/peak/plans",
    params={"date": "YYYY-MM-DD"},
    headers={"Authorization": f"Bearer {token}"},
    timeout=12,
    follow_redirects=True,
)
response.raise_for_status()
payload = response.json()
```

Observed shape: `payload["plans"]` is a list of plans with `date`, `time_slot`, `instructor_id`, `instructor_name`, `description`, `exercises`, `completed_exercises`, `extra_exercises`, and update timestamps. `payload["slots"]` contains scheduled instructors by time slot. If the user names a teacher, filter locally by `instructor_name` or `instructor_id`; an `instructor=이름` query parameter may be ignored by the API and still return all plans. Format the answer as a compact Korean workout plan: date/time slot/instructor, description if present, numbered exercises, notes, and completion status.

See `references/peak-plans-endpoint.md` for the verified endpoint notes.

## Read-only record lookup

For leaderboard-style record questions like “오늘 제자리멀리뛰기 기록”, prefer the live Peak records path first. If the API does not expose a dedicated event leaderboard, aggregate from active Peak students using `/peak/records?student_id=...`, match the event name exactly, and sort by the event's scoring direction.

## Survey / questionnaire response audits

When the user uploads a survey workbook and asks for responses that look unreliable, misread, or logically inconsistent, audit the rating block instead of treating every response as equally valid. Use the response-audit heuristics in `references/survey-response-audit.md`:

- separate mechanically uniform responses from mixed responses;
- check **question-by-question logic first**, then compare across the satisfaction / recommendation / re-enrollment / positive-word-of-mouth block;
- do not label a response as “불만” just because one item is low; only flag it when the surrounding items and the wording truly conflict;
- treat one-off extreme values as possible outliers;
- describe the result as `신빙성이 낮아 보이는 응답`, `질문을 잘못 이해했을 가능성`, `논리 충돌 후보`, or `재검토 후보` rather than accusing the respondent.

When the user asks to “정리해서 달라”, prefer a **compact grouped output** over long prose. A good default is:

1. 강한 불만형
2. 논리적으로 다시 봐야 하는 응답
3. 직선응답 의심형
4. 정상/보류

When summarizing, cite the timestamp and the exact item(s) that triggered the flag. If the respondent shows a mostly positive block but one late-item contradiction (for example 만족·추천은 높고 특정 문항만 급락), classify it as a **논리검토 필요** case, not as a blanket complaint.

For counseling spreadsheets that use the satisfaction/recommendation/retention block, keep the language neutral and factual; avoid overclaiming that the student “불만이 있다” unless the contradiction is broad and repeated across related items.

For current-enrolled aggregate questions like “현재 재원생들 남여 따로 제멀 최근기록 평균”, do **not** route through 월말테스트 unless the user explicitly says 월말테스트. Use the active Peak student list, fan out to each student's records, pick one record per student for the requested event, and compute gender-separated averages. Interpret common shorthand: `제멀` → `제자리멀리뛰기`; typo-like `최든기록` usually means `최근기록` if the surrounding phrase says 평균/현재 재원생, but mention that `최고기록` can be recalculated separately if needed. If auth is expired, stop cleanly with `/academy login`; do not invent averages.

When a single-student lookup misses the exact name, try shorter live PACA substrings before giving up. If a near-match exists, present it as a candidate with a caveat instead of forcing the user to repeat immediately. See `references/student-record-lookup-fuzzy-match.md` for the verified fallback pattern.

If the user asks for the records **as an image** (e.g. “정리해서 이미지로 줘”), do not stop at a text summary and **do NOT hand-build HTML/canvas in execute_code**. Use the `academy_report_image` tool: gather the rows from the live data, then call it with `columns` (each event + unit), `groups` (e.g. 남학생/여학생, each with `avg_label`), and `rows` (per student). The tool guarantees header↔value column alignment, gender-separated averages, a bright trendy light design, and the brand stamp. Only fall back to manual rendering if that tool is unavailable.

See `references/record-lookup.md` for the data pattern.
See `references/current-enrolled-event-averages.md` for the current-enrolled gender-average pattern.

For **single-student recent-record trend images** (one student, several events, latest 5 dates), see `references/student-record-trend-graph.md`.

## Monthly test aggregates and school-filtered tables

Use this section for Peak 월말테스트 questions about a school's students or a full event summary.

- The user does NOT have to name an event. If no school and no event are named, summarize **all events for all participants** — never ask "which event?" when they said 전체/전부/다.
- If the user names a specific school, filter by **normalized exact school name** (compare to the exact requested name; do not broaden a partial/prefix match, or similarly-named schools can mix in). Do not assume any particular school — use whatever school the user actually names this turn.
- When the user corrects the target school, acknowledge briefly and regenerate, don't re-explain the earlier mistake.
- For monthly-test participant records, use each event's `record_type_id` as the key into `participant.records`.
- When the user says `전체 종목`, `종목별`, `전체`, generate the full event list and report **남학생 / 여학생** separately (gender-separated averages by default; merge only when the user explicitly asks overall-only).
- **If producing a Discord image, use the `academy_report_image` tool** — pass `columns` (each event + unit, with `best` direction high/low), `groups` (남학생/여학생, each with `avg_label`), and `rows` (per student). Do NOT draw the table yourself in execute_code; the tool handles alignment, averages, trendy design, and stamp.

See `references/monthly-test-all-events-summary.md` and `references/monthly-test-school-filtered-records.md` for the data shape (school/event are examples only — use the user's actual values).

## Read-only staff schedule retrieval

For questions like “내일 누가 근무해”, “오늘 근무자”, or “어제 누가 출근했어”, resolve the relative date first and query the live staff-schedule data for that day. The public wrapper expects an explicit `YYYY-MM-DD` value, so do not bounce the user back for a date when the relative day is already clear.

See `references/staff-schedule-relative-dates.md` for the verified lookup pattern.

## Read-only attendance retrieval

For today's attendance, use Peak's read endpoint with the stored bearer token:

```python
import datetime, httpx
from plugins.academy_ops.auth_store import load_bindings, decrypt_token
from plugins.academy_ops.paca_config import resolve_paca_base_url

binding = next(iter(load_bindings().values()))
token = decrypt_token(binding.token_ciphertext)
base = resolve_paca_base_url()
date = datetime.date.today().isoformat()
response = httpx.get(
    f"{base}/peak/attendance/students",
    params={"date": date},
    headers={"Authorization": f"Bearer {token}"},
    timeout=12,
    follow_redirects=True,
)
response.raise_for_status()
payload = response.json()
```

Expected shape: `payload["slots"]` contains time slots such as `morning`, `afternoon`, `evening`; each student row may include `student_name`, `school`, `grade`, and `attendance_status` values such as `present`, `late`, or `absent`.

## Response format for attendance

Keep the user-facing answer compact and operational:

1. Date and source basis.
2. Slot counts.
3. Status counts.
4. Names grouped by status.
5. Mention only actionable exceptions if needed.

Preferred Korean labels:

- `present` → 출석
- `late` → 지각
- `absent` → 결석
- missing/unknown → 미확인

## Attendance image QA

When generating academy attendance or attendance-roster images for Discord, run a visual QA pass before delivery. Specifically verify that:

- The date chip is fully inside its card and visually centered.
- Class headers such as `오후반 출석예정` are fully inside their cards and centered.
- Title, subtitle, and card text are not clipped, left-shifted, or touching edges.

If any text is clipped or misaligned, regenerate the image and re-check the final render before returning it.

## Relative-date roster requests

When the user says things like `이번주 수요일`, `다음주 월요일`, or `오늘 출석할 학생 명단 이미지로 줘`, resolve the date yourself first and then call `academy_class_roster_range` with explicit `start_date` / `end_date`.

- Use the live system date to compute the target day.
- Keep `with_roster=true` when the user wants the actual student list/image.
- For future dates, prefer the class roster path even if check-in attendance is still zero; that is the point of a "should attend" query.
- Do not bounce the user back for YYYY-MM-DD when the relative day is obvious.
- If the tool complains about missing dates, that is a tool-argument issue: compute the date locally and retry instead of asking the user again.
- If the roster request runs in a local verification context and the wrapper cannot infer the Discord binding, fall back to the stored academy binding/token and continue with the read-only roster lookup rather than telling the user the data is unavailable.
- If the roster request returns an auth-expired / relink-needed message, do **not** present it as a roster absence problem; tell the user to run `/academy login` and stop.
- For image requests, return exactly one roster artifact/`MEDIA:` line, not multiple variants.
- If the public `academy_class_roster_range` wrapper cannot accept an image flag or only returns JSON/text, do not give up. Fetch the class roster with the stored academy token, convert it to the attendance-day renderer payload shape with future students marked `unknown`/`미체크`, render with `AttendanceDayRosterImageRenderer`, then run visual QA before returning. See `references/class-roster-image-fallback.md`.

See `references/attendance-relative-date-image.md` for the session-specific note.
See `references/relative-weekday-roster-fallback.md` for the explicit weekday-resolution + auth-failure fallback pattern.
See `references/class-roster-image-fallback.md` for the roster-image renderer fallback when the wrapper does not directly create an image.

## Pitfalls

- Do not treat a failed agent tool wrapper as proof that PACA/Peak is not linked. Check `~/.miho/academy_ops/bindings.json` and verify the bearer token against a read endpoint.
- If the consultation-note save wrapper asks again for the student name even though it was already in the user message, treat that as argument propagation failure. Resolve the student explicitly, then save to the local repository.
- For Peak/PACA API calls, the token worked as `Authorization: Bearer <token>`; `x-access-token` returned unauthorized in the observed flow.
- AcademyOS frontend lint: for Next.js App Router internal navigation, use `next/link` instead of raw `<a href="/...">`; when a `useEffect` calls a local loader function, stabilize that loader with `useCallback` and include it in the dependency list before running `pnpm lint`/build.
- Avoid exposing tokens, raw ciphertext, phone numbers, or unnecessary personal data in Discord replies. Return only the fields needed for the request.
- If an auth/login flow is local or tunneled, do not ask the user to paste passwords or tokens into chat.

## References

- `references/attendance-roster-routing.md` — routing note for attendance-vs-roster questions.
- `references/weekly-roster-routing-note.md` — weekday-to-ISO-date reminder for roster image requests.
