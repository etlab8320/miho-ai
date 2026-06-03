# 생기부 PDF 저장 패턴

Session lesson:
- 사용자가 업로드한 `학교생활세부사항기록부(학교생활기록부II)` PDF는 상담 메모가 아니라 **생기부 문서 저장 작업**으로 본다.
- 저장 대상은 `ConsultationNoteRepository`가 아니라 `plugins.life_record`의 문서 DB다.
- 원본 PDF는 그대로 아카이브하고, 식별 정보(학생명 / 학교명 / 학년 / 반 / 문서일자)를 추출해 `life_records.sqlite3`에 문서 레코드로 남긴다.
- 라이브 PACA/API 연결이 끊겨 부가 조회가 안 돼도, 문서 자체의 식별 정보가 보이면 로컬 life_record DB 저장은 계속 진행한다.

Verified local save shape:

```python
from pathlib import Path
import json
from plugins.life_record.repository import save_import, latest_document, db_path

bundle_dir = Path("~/.miho/.../life_record/<thread-or-student-bundle>").expanduser()
pdf_path = Path("~/.miho/cache/documents/<uploaded>.pdf")

consensus = {
    "identity": {
        "name": {"value": "김동혁", "confidence": 1.0},
        "school_name": {"value": "운유고등학교", "confidence": 1.0},
        "class_no": {"value": "2", "confidence": 1.0},
        "student_no": {"value": "4", "confidence": 1.0},
        "birth6": {"value": "", "confidence": 0.0},
    },
    "grades": [],
    "notes": [],
    "attendance": [],
    "awards": [],
}

result = save_import(
    bundle_dir=bundle_dir,
    pdf_path=pdf_path,
    page_count=16,
    raw_text=json.dumps({"document_type": "school_life_record"}, ensure_ascii=False),
    metadata={"source": "government24"},
    consensus=consensus,
    source_thread="discord:<channel>:<thread>",
)

doc = latest_document(db_path(bundle_dir))
```

Verification step:
- Read back `latest_document()` or query SQLite to confirm `student_name`, `school_name`, `page_count`, `source_pdf_path`, and `stored_pdf_path`.
- Final user reply should stay short: DB path, document id, student, school, page count, and archived PDF path.

Pitfall:
- Do **not** route this kind of file into the consultation-note DB just because the user said “db에 저장” generically. For uploaded 생기부 PDFs, the default DB is the life-record document store.
