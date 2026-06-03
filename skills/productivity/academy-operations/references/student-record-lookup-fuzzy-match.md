# Student record lookup fuzzy-match fallback

Observed lookup pattern from a live session:

- User asked for `박서현 학생 기록 조회`.
- `academy_student_record_lookup` with `student_query=박서현` returned `학생을 찾지 못했어. 이름이나 학교를 조금 더 정확히 알려줘.`
- A direct PACA search showed no exact `박서현`, but substring inspection of the current student list revealed a likely nearby match: `백서현(백마고, 고3)`.

## Rule

When a student record lookup does not return an exact match:

1. Try a live PACA search using shorter substrings from the name.
2. Prefer an exact name match if one exists.
3. If only a near-match exists, present it as a candidate, not as fact.
4. Do not ask the user to repeat immediately unless the live search yields multiple plausible candidates or none at all.

## Reply pattern

- Exact miss + one strong candidate: `박서현은 정확히 안 잡혀. 비슷한 이름으로 백서현(백마고, 고3)이 보여. 이 학생 조회할까?`
- Exact miss + no candidate: ask for a more precise name or school.
- Ambiguous candidates: list the candidates and ask the user to choose.
