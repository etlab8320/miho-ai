# 생기부 PDF 교체 저장 — 스캔본/이미지 PDF 패턴

Session lesson:
- 사용자가 새 생기부 PDF를 올리고 “저장해줘 아까껀 지우고”라고 하면, 같은 스레드의 기존 `life_record/*` 활성 번들을 먼저 제거한 뒤 새 PDF를 저장한다.
- “지우고”는 활성 저장본에서 제거한다는 뜻이다. 임시 quarantine으로 옮겼다면 최종적으로 실제 삭제까지 확인하거나, 삭제 대신 보관했다는 사실을 명확히 말해야 한다.
- 스캔본 PDF는 `PyMuPDF page.get_text()`가 빈 문자열일 수 있다. 이때 저장을 중단하지 말고 첫 페이지를 이미지로 렌더링해 학생 식별 정보만 비전으로 읽은 뒤 원본 PDF를 아카이브한다.

Verified fallback flow:

```python
from pathlib import Path
import fitz

pdf_path = Path("~/.miho/cache/documents/uploaded.pdf").expanduser()
first_png = pdf_path.with_name(pdf_path.stem + "_first_page.png")
doc = fitz.open(str(pdf_path))
page_count = doc.page_count
pix = doc.load_page(0).get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
pix.save(str(first_png))
doc.close()
```

Then inspect `first_png` with vision and extract only:
- 학생명
- 학교명
- 현재 학년/반/번호
- 생년월일 앞 6자리 if visible
- 문서일자 if visible

Minimal save is acceptable when full OCR/section extraction was not requested:

```python
consensus = {
    "identity": {
        "name": {"value": "김동혁", "confidence": 1.0},
        "school_name": {"value": "운유고등학교", "confidence": 1.0},
        "class_no": {"value": "2", "confidence": 1.0},
        "student_no": {"value": "4", "confidence": 1.0},
        "birth6": {"value": "080317", "confidence": 1.0},
    },
    "grades": [],
    "notes": [],
    "attendance": [],
    "awards": [],
}
```

Save with `plugins.life_record.repository.save_import(...)`, preserving the original PDF in `sources/<hash>_original.pdf`. Use `extraction_method` such as `first_page_vision_identity_only_v1` and metadata noting that this was an identity-only scanned-PDF save.

Verification:
- Query the `students` table joined with `student_documents`, not just `latest_document()`, because `latest_document()` may omit `class_no`/`student_no` in its selected columns.
- Verify `name`, `school_name`, `class_no`, `student_no`, `birth_masked`, `page_count`, and `stored_pdf_path`.

Final reply should be short and operational:
- 저장 완료 / 이전 활성 저장본 삭제 완료
- 학생, 학교, 학년·반·번호, 페이지 수
- DB path and archived PDF path

Privacy:
- Do not print full 주민등록번호. Store/display only masked birth (`YYMMDD-*******`) if needed.
