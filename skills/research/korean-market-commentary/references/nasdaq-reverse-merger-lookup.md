# NASDAQ reverse-merger ticker clue lookup

Use this when the user gives a loose clue such as “NASDAQ, starts with C, preparing a reverse merger” and wants the likely ticker quickly.

## Fast workflow

1. Search broad web/news first with exact catalyst language:
   - `"reverse merger" "Nasdaq" "C" stock`
   - `"proposed reverse merger" "Nasdaq" "ticker" "C"`
   - `"reverse merger" "Nasdaq" "closing" "C"`
2. If generic search is noisy, search authoritative filings/news pages:
   - SEC full-text endpoint: `https://efts.sec.gov/LATEST/search-index`
   - Query examples: `"reverse merger" "Nasdaq"`, `"proposed reverse merger"`, `"reverse merger" "letter of intent"`
   - Filter by recent dates and forms likely to carry transaction disclosures: `6-K`, `8-K`, `DEFM14A`, `S-4`, `F-4`.
3. Confirm the candidate through at least two sources:
   - Official company/transaction press release.
   - SEC filing or filing mirror showing the same proposed transaction.
   - Market data source verifying ticker, exchange, and company name.
4. Distinguish status clearly:
   - `rumor` / `non-binding term sheet` / `definitive agreement signed` / `shareholder vote pending` / `closed`.

## Example pattern captured

For clue “NASDAQ, starts with C, preparing reverse merger,” a strong candidate was `CURR` / Currenc Group Inc. because official Animoca Brands material and SEC 6-K mirrors described a **proposed reverse merger with Animoca Brands**. The key evidence points were:

- Currenc to acquire 100% of Animoca Brands shares via proposed reverse merger.
- Combined entity expected to be Nasdaq-listed.
- Animoca shareholders expected to own ~95%; existing Currenc shareholders ~5%.
- Exclusivity/negotiation period and target closing dates showed it was still in-progress, not completed.

## Reporting style

For the user, lead with the likely ticker and confidence, then give concise evidence and risk flags. Avoid overlong market education unless asked.
