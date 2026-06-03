# Monthly test school-filtered record tables

특정 학교 학생들의 Peak 월말테스트 기록을 표/이미지로 요청할 때 사용. **특정 학교명을 가정하지 말고, 사용자가 이번 턴에 실제로 말한 학교를 그대로 쓴다.**

## Key lesson

사용자가 정확한 학교명을 말하면 **정규화된 정확 일치**로 필터하라. 부분/접두(prefix) 일치로 넓히지 마라 — 이름이 비슷한 다른 학교(예: 같은 지역명으로 시작하는 학교들)가 섞여 잘못된 결과가 나온다.

## Reliable flow

1. `list_peak_monthly_tests()` 로 월별 테스트를 받아 요청한 월/상태 선택.
2. `get_peak_monthly_test_records(test_id)`.
3. 사용자가 학교를 말한 경우에만, 정규화(공백 제거·소문자화) 후 **정확 일치**로 participants 필터. 부분 `contains` 필터는 사용자가 명시적으로 "그 지역 전체"를 요청할 때만.
4. `participants[].records` 를 `record_types` 의 `record_type_id` 키로 읽어 rows 구성 (월말테스트 row `id` 아님).
5. **이미지를 원하면 `academy_report_image` 도구를 사용**한다 — 직접 HTML/코드로 표를 그리지 말 것. `columns`(종목+단위, best 방향), `groups`(남학생/여학생, 각 `avg_label`), `rows`(학생별)로 넘기면 정렬·성별 평균·트렌디 디자인·스탬프를 도구가 보장한다.

## Pitfalls

- `record_types` 항목은 `id` 와 `record_type_id` 를 모두 가짐; participant `records` 는 `record_type_id` 로 키.
- 이름이 비슷한 학교가 같은 데이터에 있을 수 있으니, 사용자가 말한 학교명과 **정확히** 일치하는 것만.
- 사용자가 대상 학교를 정정하면 짧게 인정하고 정확히 재생성한다 (이전 실수를 길게 설명하지 말 것).
