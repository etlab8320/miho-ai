# Pixel Document Evidence Spec

## Problem

PDF, web, MHTML, and scanned documents lose important table, chart, and layout evidence when routed through text-only extraction. Admissions guides and student records need page-level visual evidence so Miho and ET Dev OS can verify numbers against the original source.

## Users And Jobs

- Miho Discord users upload or reference documents and need grounded answers with page evidence.
- ET Dev OS needs a reusable local command to inspect university tables and scanned source material before coding or reporting.
- Reviewer agents need machine-readable evidence: page image, OCR text, coordinates, and source hash.

## Scope

### In

- Render PDF pages and image/scanned files into page evidence images.
- Extract text layer when available and use Apple Vision OCR when installed.
- Store source hash, page image paths, OCR spans, text excerpts, and manifest path under `MIHO_HOME`.
- Provide one Miho core tool: `pixel_document_evidence`.
- Provide one ET Dev OS-friendly CLI: `scripts/pixel_document_evidence.py`.
- Return provisional but usable results when OCR or browser rendering is unavailable.

### Out

- Full browser-pixel rendering for every dynamic website.
- Excel/HWP semantic table normalization.
- Long-term memory storage of document contents.

## Acceptance Criteria

- `pixel_document_evidence action=status` reports PDF/image/OCR capability without throwing.
- `action=ingest` accepts local HTML/MHTML text fallback, PDF, image, and URL sources.
- Ingested manifests contain schema version, source hash, page images, page text, OCR status, and reviewer guidance.
- `action=search` returns page image evidence and excerpts, not text-only answers.
- Image/scanned sources without Apple Vision still return `provisional` with a clear retry path.
- The tool is visible in `miho-cli` and `miho-discord` toolsets.
- ET CLI can call the same service code.

## Domain Model

- Document manifest: schema version, document id, source metadata, render status, OCR status, pages.
- Page evidence: page number, image path, dimensions, page text, text source, OCR spans, source hash.
- Search result: page number, excerpt, page image path, optional crop path, reviewer requirement.

## API Contract

Single tool: `pixel_document_evidence`

- `status`: no required args.
- `ingest`: `source`, optional `max_pages`, `ocr_backend`, `languages`.
- `search`: `document_id` or manifest path plus `query`, optional `limit`.
- `review`: evidence payload plus optional answer text.

All failures return Korean plain-language `message_ko` and never expose stack traces.

## UI Contract

Discord/CLI responses should mention page/crop evidence paths and whether the result is ready or provisional. User-facing copy should not say the system failed; it should give the current evidence and next retry route.

## Test Plan

- Unit: renderer text fallback and image provisional path.
- Unit: search returns page image evidence.
- Tool: status/ingest/search dispatch returns JSON contract.
- Toolset: `miho-cli` and `miho-discord` expose the tool.
- Plugin: backend plugin registers reviewer auxiliary task.

## Implementation Tasks

- [ ] T1: Add Pixel Document service and storage contract.
  - Files: `plugins/pixel_documents/*`
  - Tests: `tests/plugins/test_pixel_documents.py`
  - Acceptance: manifests are stable and searchable.
- [ ] T2: Add core Miho tool wrapper.
  - Files: `tools/pixel_document_tool.py`, `toolsets.py`
  - Tests: `tests/tools/test_pixel_document_tool.py`
  - Acceptance: status/ingest/search work and toolsets expose the tool.
- [ ] T3: Add ET Dev OS CLI wrapper.
  - Files: `scripts/pixel_document_evidence.py`
  - Tests: covered through same service contract.
  - Acceptance: CLI delegates to the same implementation.

## Risks

- Apple Vision requires macOS PyObjC bindings; the backend must be optional and report availability.
- Browser-perfect web screenshots need Playwright/Chromium or an approved native renderer; fallback must be labeled reduced-confidence.
- Document contents may include PII; store under `MIHO_HOME` only and do not write to memory.
