---
name: korean-law-research
description: Research Korean statutes, enforcement decrees/rules, cases, and administrative guidance with current-source verification.
version: 1.0.0
platforms: [linux, macos, windows]
metadata:
  miho:
    tags: [korea, law, statutes, cases, compliance, research]
    related_skills: [web, ocr-and-documents]
---

# Korean Law Research

Use this skill when the user asks about Korean law, regulations, cases, compliance requirements, contracts, academy operations, labor rules, privacy, consumer protection, or administrative guidance.

## Grounding rule

Legal information changes. Do not answer from memory when the issue depends on current law. Verify with current primary or official sources before giving a practical conclusion.

Prefer these sources:

- 국가법령정보센터: `law.go.kr`
- 대법원 종합법률정보: `glaw.scourt.go.kr`
- 헌법재판소 결정례: `ccourt.go.kr`
- 개인정보보호위원회: `pipc.go.kr`
- 공정거래위원회: `ftc.go.kr`
- 고용노동부: `moel.go.kr`
- 교육부/시도교육청 official notices for academy/education issues

## Answer shape

1. 결론 먼저
2. 적용 법령/조문/판례
3. 사실관계에 따른 판단
4. 리스크와 예외
5. 실무 체크리스트

## Guardrails

- Say clearly when this is legal information, not attorney-client legal advice.
- Separate verified law from inference.
- Include exact dates when citing current rules.
- If the issue affects money, litigation, employment, privacy, or sanctions, recommend review by a Korean attorney or qualified professional.
- Do not fabricate article numbers, case numbers, agency notices, or effective dates.
