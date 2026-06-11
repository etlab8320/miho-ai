# Life Record Source-First Ingestion Spec

## Problem
Chrome-saved NEIS MHTML uploads can be correctly routed to `life_record_ingest_pdf`,
but text extraction may spend 180 seconds per retry and repeat the same failing
LLM call. This blocks Discord responses and does not improve accuracy.

## Scope
### In
- Preserve original MHTML/PDF source files.
- Extract deterministic identity, attendance, grades, notes, and raw sections from NEIS+ MHTML tables.
- Avoid MHTML-to-PDF conversion when table extraction succeeds.
- Replace stale MHTML rows on re-ingest so central data matches the latest source file.
- Store PDF profile photos when the PDF embeds a real student photo.
- Keep MHTML profile-photo extraction conservative: do not store NEIS UI icons/logos as student photos.
- Sync Hermes-only student DB rows into Miho central when explicitly requested.

### Out
- Replacing the PDF text/vision consensus path with an unverified local table parser.
- Claiming browser-rendered MHTML screenshots contain a student photo when the MHTML archive only contains UI assets.
- Adding new frontend/API surfaces.

## Acceptance Criteria
- Table-rich MHTML ingestion does not call Chrome, PDF conversion, PDF extraction, page rendering, OCR, or LLM extraction.
- Re-ingesting the same stored MHTML original is idempotent and does not fail on same-file copy.
- Re-ingesting a newer MHTML for the same student removes superseded thread rows and replaces central rows.
- Transfer-school records prefer the latest `전입학` high school over an older `입학` high school.
- Attendance detail columns are persisted, not collapsed into a string note.
- Existing PDF accumulation behavior remains unchanged.
- Hermes student-level coverage in Miho central is 100% after explicit sync.

## Test Plan
- Unit-test MHTML table parsing for identity, attendance details, grades, notes, and transfer-school selection.
- Integration-test MHTML ingest without conversion/rendering/LLM calls.
- Integration-test stored-original re-ingest and central row replacement.
- Run existing life-record routing, context, and ingest tests.

## PDF Fast Path Note
Text-layer PDFs are currently handled by the existing exact-text plus consensus
path, and real embedded profile photos are extracted through PyMuPDF. A pure
Python PDF table fast path was explored against 기아림/박시현/김서연 samples, but
PyMuPDF table detection missed rows in some real PDFs. Keep that path disabled
until sample parity reaches 100% against verified DB counts.
