# Naver Finance / KRX quick extraction notes for Korean market commentary

This note is for fast, repeatable market reads when the user asks why KOSPI/KOSDAQ moved.

## Primary live source

- Naver Finance KOSDAQ page:
  - `https://finance.naver.com/sise/sise_index.naver?code=KOSDAQ`
- The page body text usually contains the most useful fields in a single block:
  - latest close / intraday value
  - percent change
  - trading volume and trading value
  - high / low
  - 52-week high / low
  - advance / decline breadth
  - investor flows: 개인 / 외국인 / 기관
  - program trading
  - headline list under 시황뉴스

## Fast extraction pattern

When using browser tools, the simplest method is often:

```js
document.body.innerText
```

Then search visually for these labels:
- `장마감`
- `상승종목수` / `하락종목수`
- `개인` / `외국인` / `기관`
- `프로그램 매매동향`
- `시황뉴스`

## Example of useful output shape

A typical body text block includes lines like:
- `2026.05.27 장마감`
- `1,133.13`
- `39.39 -3.36%`
- `상승종목수 192`
- `하락종목수 1507`
- `외국인 -847억`
- `기관 -5,411억`

These are the minimum facts needed to explain a broad selloff without over-guessing.

## Commentary rules

- If 코스닥 falls while 코스피 is strong, treat it as a **rotation / style** story first.
- If 외국인과 기관이 동반 매도하고 breadth is weak, say the move was **supply-led**.
- If only headlines are available but breadth/flows are missing, label the explanation as **tentative**.
- Do not attribute the move to one article title when the broader flow data points elsewhere.

## Suggested answer structure

1. One-line bottom line.
2. 2–4 bullets:
   - 수급
   - 업종 회전
   - 해외/매크로
   - notable exception or caveat
3. Optional: what to watch next session.

## Practical note

For quick reads, `browser_console` on the finance page is often cleaner than scraping search results, because it captures the page's already-rendered market summary in one block.