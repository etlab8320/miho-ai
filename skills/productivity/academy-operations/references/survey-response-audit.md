# Survey response audit notes

Use this when the user uploads an academy questionnaire / satisfaction survey workbook and asks to separate answers that look unreliable, misread, or emotionally charged.

## Observed workbook shape

- Single sheet workbook
- Header row in row 1
- One respondent per row starting at row 3
- Demographics in the first columns; Likert-style academy evaluation items follow
- In the observed file, rows 3–22 contained 20 responses and the rating block spanned 44 statements

## Suggested triage buckets

1. **Low-confidence / mechanically uniform**
   - Entire rating block is the same value across all questions, especially all `매우 그렇다.`
   - Not proof of bad faith, but it has low diagnostic value and should be separated from richer responses.

2. **Strong complaint signal**
   - Multiple negative items cluster around the same theme: cost, access, management, feedback, recommendation intent, or overall satisfaction.
   - Treat as a real dissatisfaction signal unless the rest of the response is clearly inconsistent.

3. **Single-item outlier**
   - One value sharply disagrees with an otherwise consistent pattern.
   - Mark as possible misclick / fatigue / one-off complaint.

4. **Potential misunderstanding**
   - The respondent’s pattern does not match the question theme, or the answer set appears to respond to a different construct than the prompt asked.
   - Phrase carefully as "질문을 잘못 이해했을 가능성" rather than a hard accusation.

## Output guidance

- Do **not** label a response as fake or dishonest.
- Prefer wording like:
  - `신빙성이 낮아 보이는 응답`
  - `질문과 대조했을 때 논리적으로 어긋나는 항목`
  - `학원 불만이 강하게 드러나는 응답`
  - `재검토 후보`
- When possible, cite the exact timestamp and the specific item(s) that triggered the flag.
- If several responses are identical across all rating items, note them as a **mechanically uniform cluster** rather than repeating the same criticism one by one.

## Quick heuristics from the observed file

- A fully uniform 44-item `매우 그렇다.` response is a common low-confidence pattern.
- Negative clusters around `비용 대비 가치`, `개별관리`, `피드백`, `추천 의향`, and `전반 만족` are the clearest complaint signatures.
- A response with one extreme negative value and all other items positive is worth calling out as a single-item anomaly.
