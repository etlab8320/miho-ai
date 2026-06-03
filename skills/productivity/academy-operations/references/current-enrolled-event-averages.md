# Current-enrolled event averages

Use this when 맥스 asks for aggregate practical-test records across **현재 재원생** by gender, such as:

- `현재 재원생들 남여 따로 제멀 최근기록 평균`
- `남학생/여학생 제자리멀리뛰기 평균`
- `현재 애들 최고기록 평균`

## Routing

This is a **Peak student-record aggregate**, not necessarily a 월말테스트 query. Do not use monthly-test participant data unless the user explicitly says 월말테스트 / 월말평가 / 특정 테스트.

## Event shorthand

- `제멀` = `제자리멀리뛰기`
- `최든기록` in this context is likely a typo for `최근기록`. If the answer depends on recent vs best, default to the word that best fits the phrase and briefly say it can be recalculated as 최고기록 if intended.

## Data pattern

1. Load the stored PACA/Peak binding and bearer token.
2. Fetch active Peak students (`client.list_peak_students()` / `/peak/students`).
3. For each active student, fetch records (`client.list_peak_records(peak_student_id)` / `/peak/records?student_id=...`).
4. Filter records by exact event name, e.g. `제자리멀리뛰기` from `record_type_name` or `event_name`.
5. Pick **one record per student**:
   - `최근기록`: newest `measured_at` / `date` / created timestamp.
   - `최고기록`: best value by event direction; for 제자리멀리뛰기, higher is better.
6. Split by gender from the student profile. If gender is missing/unknown, report excluded/unknown count separately rather than guessing.
7. Compute averages only from students with a valid numeric record.

## Response shape

Keep it compact and operational:

```text
현재 재원생 기준 / 제자리멀리뛰기 / 최근기록

- 남학생: 평균 000cm / 기록 있는 학생 00명
- 여학생: 평균 000cm / 기록 있는 학생 00명
- 제외: 기록 없음 00명, 성별 미확인 00명
```

Add a short caveat only if needed: `최든기록을 최고기록 의미로 말한 거면 바로 다시 최고기록 기준으로 뽑으면 돼.`

## Auth failure

If the live API returns an expired-link/login error, stop cleanly with `/academy login` and do not produce estimated averages. This is a real-student data question, so fabricated averages are worse than no answer.
