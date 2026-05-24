---
name: korean-tax-research
description: Research Korean tax rules, filing duties, VAT/income/corporate tax, academy tax issues, and National Tax Service guidance.
version: 1.0.0
platforms: [linux, macos, windows]
metadata:
  miho:
    tags: [korea, tax, nts, vat, income-tax, corporate-tax, withholding]
    related_skills: [korean-law-research, ocr-and-documents]
---

# Korean Tax Research

Use this skill when the user asks about Korean tax, VAT, income tax, corporate tax, withholding, payroll, invoices, academy tax operations, expense treatment, or filing calendars.

## Grounding rule

Tax rules and filing thresholds change. Verify current rules with official sources before producing a conclusion.

Prefer these sources:

- 국세청: `nts.go.kr`
- 홈택스: `hometax.go.kr`
- 국세법령정보시스템: `txsi.hometax.go.kr`
- 국가법령정보센터: `law.go.kr`
- 기획재정부 tax materials: `moef.go.kr`
- 지방세: `wetax.go.kr`

## Answer shape

1. 결론 먼저
2. 세목과 과세기간
3. 관련 법령/예규/국세청 안내
4. 계산 구조 또는 신고 절차
5. 필요 서류와 마감일
6. 리스크/세무사 확인 포인트

## Guardrails

- Do not present tax advice as a final professional opinion.
- Verify dates, thresholds, rates, and filing deadlines before stating them.
- Separate law, NTS guidance, and practical inference.
- For penalties, audits, large money, or ambiguous classification, recommend a Korean tax accountant or tax attorney.
- Avoid invented examples unless clearly marked as examples.
