---
name: korean-market-commentary
description: Explain Korean stock market moves and sector rotations using live market data and news, with concise Korean commentary.
---

# Korean Market Commentary

Use this skill when the user asks why KOSPI/KOSDAQ moved, what drove a sector rotation, whether a selloff was broad-based, or wants a short market read for Korean equities.

## Core intent

Give a fast, evidence-backed explanation that separates:
- **confirmed drivers** from **plausible interpretation**
- **index-level movement** from **sector / stock-level rotation**
- **headline noise** from **actual market mechanics**

## Workflow

1. **Anchor the market state first**
   - Verify the latest close / intraday state from a live market source.
   - Check the index level, percent change, market breadth, and investor flow.
   - For Korean markets, prefer KRX / Naver Finance / reputable financial news.

1a. **If the user gives a loose ticker/catalyst clue, identify before analyzing**
   - For clues like “NASDAQ, starts with C, reverse merger 준비 중,” first find the most likely ticker; do not jump into general market commentary.
   - Use exact catalyst searches plus authoritative confirmation: official company press release, SEC 6-K/8-K/S-4/F-4, and a market data source verifying ticker/exchange/company name.
   - State confidence and transaction status clearly: rumor, non-binding term sheet, definitive agreement, vote pending, or closed.
   - See `references/nasdaq-reverse-merger-lookup.md` for a compact reverse-merger clue lookup recipe and an example pattern.

2. **Check the three usual drivers**
   - **수급**: 개인 / 외국인 / 기관, and if available program trading.
   - **업종 회전**: which sectors were strong or weak.
   - **매크로/해외 변수**: U.S. indices, rates, FX, risk-on / risk-off tone.

3. **Read news as evidence, not as the whole cause**
   - A headline alone is not a full explanation.
   - If possible, corroborate with flows and breadth before attributing causality.
   - If multiple articles point to the same theme, say it is a **dominant market narrative**, not a proven single cause.

4. **Form the explanation hierarchically**
   - Start with the **one-line bottom line**.
   - Then give 2–4 bullets in this order:
     1. market structure / 수급
     2. sector rotation
     3. macro or overseas catalyst
     4. notable exceptions or counter-signals
   - End with a short forward-looking note if the user asked for it.

## Answer style

- Default to **natural Korean**.
- Be **concise and execution-focused**.
- Use plain language: “돈이 어디로 갔는지”, “왜 지수가 밀렸는지”, “어떤 업종이 받쳤는지”.
- Avoid overexplaining when the user asked for a quick reason.
- If the user wants more detail, expand into sector-by-sector or flow-by-flow analysis.

## Important guardrails

- Do **not** claim a single headline caused the whole move unless the data supports it.
- Do **not** give uncited numbers from memory when current market data is available.
- If the cause is mixed or uncertain, say so directly: “복합 요인”, “수급이 더 컸다”, “헤드라인보다 로테이션 성격이 강했다”.
- Distinguish between:
  - **장중 변동성** and **종가 기준 해석**
  - **코스피 주도 장세** and **코스닥 소외 장세**
  - **일시적 기술적 반등/차익실현** and **추세 전환**

## Verification checklist

Before answering, confirm at least one of:
- index close and percent change
- breadth / advance-decline balance
- foreign / institutional flow
- sector leadership or laggards
- a relevant market headline that matches the flows

If the evidence is thin, state the uncertainty instead of forcing a clean narrative.

## Supporting notes

- See `references/naver-finance-kosdaq.md` for a compact extraction recipe and source-specific notes.
