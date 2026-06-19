# 2027 수시 체대 OCR/evidence 재판독 전용 프롬프트

너는 미호 2027 수시 체대입시 산식의 **OCR/evidence 재판독 검증자**다.

목표는 새 결함을 많이 만드는 것이 아니라, 이전 최종 리포트에서 `OCR/evidence 품질 낮음` 또는 `PDF 이미지 직접 재판독 권고`로 남은 항목을 **PDF 원문 이미지 기준으로 다시 판독**해 계산 영향 여부를 확정하는 것이다.

## 기준 repo

```bash
git clone https://github.com/etlab8320/miho-ai.git
git clone https://github.com/etlab8320/korea-susi27-athletic-reference.git

cd miho-ai
export MIHO_SUSI27_STAGING_DB="$(pwd)/../korea-susi27-athletic-reference/runtime/susi27_pipeline/susi27_staging.sqlite3"
```

원문/런타임 위치:

- PDF 원문: `korea-susi27-athletic-reference/pdfs_official/`
- cleaned text: `korea-susi27-athletic-reference/source_texts_clean/`
- runtime DB: `korea-susi27-athletic-reference/runtime/susi27_pipeline/susi27_staging.sqlite3`
- formula runtime: `korea-susi27-athletic-reference/runtime/susi27_pipeline/susi27_university_formula_plugins.py`
- 학교별 formula: `korea-susi27-athletic-reference/runtime/susi27_pipeline/susi27_formula_*.py`
- 미호 코드: `miho-ai/plugins/susi_ops/`

## 절대 규칙

- Ground truth는 **2027 수시모집요강 PDF 원문 이미지**다.
- OCR/TXT는 검색 보조일 뿐이다. 의심되면 PDF 페이지를 이미지로 열어 눈으로 판독한다.
- 수시엔진은 사용하지 마라. 작년 합격자 총점 비교용이지 계산식 검증용이 아니다.
- 비체대 일반학과를 결함 수에 넣지 마라.
- 체육특기자/경기실적/선수전형은 일반 추천 결함 수에 넣지 마라.
- 한밭대 빅데이터헬스케어융합학과는 체대 추천 대상이 아니므로 `[대상 제외]`로 따로 판정한다.
- 경희/동명은 개별 `susi27_formula_*.py`가 아니라 통합본 `susi27_university_formula_plugins.py` 안의 `@formula` 구현을 볼 수 있다.

## 재판독 대상

아래 row를 전부 확인한다.

현재 `pdftotext` 기준 텍스트 레이어가 0줄로 나온 핵심 이미지 PDF는 **나사렛대, 배재대, 동명대**다. 이 3개교는 OCR 텍스트보다 PDF 페이지 이미지 판독을 우선한다. 나머지 학교는 텍스트 레이어가 있으나 evidence/DB 문구가 헷갈릴 수 있으므로 원문 페이지와 코드/DB를 다시 맞춘다.

| row | 학교 | 학과 | 전형 | 재판독 포인트 |
|---:|---|---|---|---|
| 106 | 나사렛대 | 재활스포츠학부 | 기초생활/차상위 | 점수구간표 OCR |
| 107 | 나사렛대 | 재활스포츠학부 | 농어촌학생 | 점수구간표 OCR |
| 108 | 나사렛대 | 재활스포츠학부 | 일반학생 | 점수구간표 OCR |
| 194 | 배재대 | 스포츠마케팅 | 교과 | 등급표 OCR |
| 195 | 배재대 | 스포츠지도건강재활 | 교과 | 등급표 OCR |
| 196 | 배재대 | 스포츠지도건강재활 | 일반고교과 | 등급표 OCR |
| 197 | 배재대 | 스포츠지도건강재활 | 지역인재I | 등급표 OCR |
| 337 | 창원대 | 체육학과 | 예체능 | evidence가 원서접수 일정 텍스트 |
| 248 | 성결대 | 체육교육과 | 농어촌학생 | `환산평균` 정의, 진로선택 포함 여부 |
| 249 | 성결대 | 체육교육과 | 실기우수자 | `환산평균` 정의, 진로선택 포함 여부 |
| 26 | 경북대 | 체육교육과 | 교과우수자 | evidence 품질, 학생부/실기/출결 구조 |
| 28 | 경북대 | 체육교육과 | 사회통합 | evidence 품질, 학생부/실기/출결 구조 |
| 99 | 공주대 | 스포츠과학과 | 일반 | rfull=301.5 변환점수표 |
| 298 | 울산대 | 스포츠과학부 | 농어촌 | 진로선택·출결 합산 구조 |
| 303 | 울산대 | 스포츠과학부 | 예체능 | 진로선택·출결 합산 구조 |
| 390 | 한밭대 | 빅데이터헬스케어융합학과 | 지역인재(교과) | 대상 제외 확정, rfull=545 참고 |
| 392 | 한밭대 | 빅데이터헬스케어융합학과 | 학생부교과 | 대상 제외 확정, rfull=545 참고 |
| 159 | 동명대 | 스포츠재활학과 | 실기 | 실기전형 반영학기 |
| 397 | 호서대 | 사회체육학과 | 실기 | 9등급 0 vs 40 |
| 416 | 호서대 | 스포츠과학과 | 실기 | 9등급 0 vs 40 |

## 각 row 필수 확인 항목

아래를 PDF 이미지 기준으로 확인한다.

- 모집단위/전형이 요강에 실제 있는지.
- 학생부 만점, 실기 만점, 출결/봉사/면접/서류 만점.
- 등급별 점수표 또는 변환점수표.
- 9등급/최저구간/0점 처리 규칙.
- 반영교과: 전과목/지정교과/상위 N/교과군별 상위 N.
- 이수단위 반영 여부: 단위수 가중평균인지 단순 평균인지.
- 진로선택 반영 여부와 A/B/C 환산표.
- 졸업예정자/졸업자 반영학기.
- 출결 산식과 학생부 총점 합산 여부.
- DB/code가 PDF 원문과 일치하는지.

## 출력 형식

각 row마다 아래 형식으로만 써라.

```md
## 학교 / row

- 대상 판정: [대상 포함 / 별도조건전형 / 대상 제외 / 계산불가전형]
- OCR 재판독 판정: [원문 확인 완료 / OCR 오염 확인 / 근거부족]
- 최종 판정: [확정일치 / 반박-오류 / 부분반박 / 대상 제외 / 근거부족]
- PDF 이미지 근거: 문서명 p.__, 짧은 원문 인용
- 코드/DB 근거: 파일:라인 또는 DB table/row
- 숫자 확인:
  - 학생부 만점:
  - 실기 만점:
  - 출결/기타:
  - 등급표/구간표 핵심:
- 계산 영향: [없음 / 있음]
- 필요한 수정:
```

## 최종 요약

마지막에 반드시 아래 표를 작성한다.

| 항목 | 수 |
|---|---:|
| 재판독 row | |
| 확정일치 | |
| 대상 제외 | |
| 반박-오류 | |
| 부분반박 | |
| 근거부족 | |
| 코드 수정 필요 | |
| DB/evidence만 정리 필요 | |

그리고 **즉시 코드 수정 TOP 10**과 **DB/evidence 정리 TOP 10**을 따로 적어라.
