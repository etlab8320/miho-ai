# Sports Performance Agent Spec

## Problem
Miho needs a PE entrance-exam motion-analysis coach agent that can use future vendor API/PDF outputs before the vendor integration exists.

## Scope
### In
- Standard motion-analysis input contract.
- Core exercise packs: standing long jump, medicine ball throw, shuttle run, back strength, sit and reach.
- PE-brain 논문 metadata/summary를 accepted evidence pack으로 동기화한다.
- Free/open-source single-camera video-analysis provider wrapper.
- A deterministic motion-context tool that standardizes vendor/manual metrics.
- A coach auxiliary agent that writes bottlenecks, cues, drills, one-week plan, avoid list, safety state, and evidence status.
- A reviewer auxiliary agent that checks structure, safety, and evidence linkage before delivery.

### Out
- Medical-grade or research-grade 3D motion capture from a single camera.
- Vendor API client.
- Full-text RAG/vector ranking. PE-brain chunk export가 확인되기 전까지는 summary-only evidence pack으로 제한한다.
- Medical diagnosis.

## Domain Model
- `sports_motion_schema`: returns supported exercises and accepted metric aliases.
- `sports_pe_brain_evidence`: syncs/searches PE-brain papers and returns only accepted evidence packs by default.
- `sports_motion_feedback`: consumes student, exercise, metrics, optional records, pain flags, and evidence refs; then calls the coach agent when LLM routing is available.
- `sports_video_analyze`: validates a stored video path, selects a free provider, and prepares or runs Sports2D+RTMPose single-camera analysis.
- `sports_performance_coach`: auxiliary task for dynamic coaching interpretation.
- `sports_performance_reviewer`: auxiliary task for safety/evidence/result review after deterministic hard gates.
- If evidence is insufficient, reviewer returns `retry_needed` with retry tools instead of ending in a dead-end failure.

## Provider Strategy
- Default provider: `sports2d_rtmpose_2d`.
- Install path: `uv sync --extra all --extra messaging --extra sports-motion`.
- `Sports2D` supplies video-to-2D-angle workflow and uses RTMLib/RTMPose as the pose engine.
- Full `mmpose` is not installed by default because it is heavier than the Mac mini runtime needs; the provider status reports `mmpose_full` if it is installed later.
- Every single-camera result is marked with `not_3d_verified`, `camera_angle_sensitive`, and `trend_more_reliable_than_absolute_value`.
- Pose2Sim remains a future 3D provider when 2+ calibrated cameras are available.

## Free Paper Search Workflow
Use free/open sources first:
- PubMed Central: free full text for sports medicine, biomechanics, rehab, injury-risk papers.
- Google Scholar: search title + `"pdf"` or use the right-side PDF link and "all versions".
- Semantic Scholar: use "PDF" and related-paper graph for newer biomechanics papers.
- DOAJ: open-access journal filter.
- RISS: Korean theses and domestic papers; prefer records with free 원문.
- arXiv/bioRxiv/medRxiv: preprints only; mark as preprint evidence, not final clinical consensus.

Suggested queries:
- `"standing long jump" biomechanics knee angle takeoff`
- `"medicine ball throw" biomechanics trunk rotation release angle`
- `"shuttle run" change of direction biomechanics knee valgus`
- `"sit and reach" pelvic tilt hamstring flexibility`
- `"back strength" isometric trunk extension testing posture`

Evidence rules:
- Store DOI/URL/title/year/population/task before using a paper in `evidence_refs`.
- PE-brain refs use `pe_brain:<paper_id>` and must pass `accepted` quality before final coaching.
- Off-domain PE-brain papers are rejected; missing-summary papers stay `review_required`.
- Do not turn a single paper into a universal prescription.
- If a paper is not open full text, use only abstract-level claims and mark evidence as incomplete.

## Acceptance Criteria
1. The plugin registers four tools and two auxiliary tasks.
2. The feedback tool accepts five core exercises and Korean aliases.
3. The tool marks missing papers as `pending_source_pack` instead of pretending evidence exists.
4. Pain flags trigger human-check safety status.
5. Coach and reviewer use auxiliary LLM agents when available and deterministic fallback only when unavailable.
6. Reviewer blocks incomplete feedback and passes complete feedback.
7. Video analysis provider status is available without importing heavy Sports2D modules.
8. Missing or invalid video paths return Korean plain-language errors, not stack traces.
9. PE-brain evidence search excludes rejected/review-required papers unless explicitly requested.
10. Rejected PE-brain refs are removed from coaching evidence without producing a dead-end answer.
11. Evidence-insufficient feedback still returns a provisional result plus retry instructions.

## Test Plan
- Unit: exercise aliases, metric normalization, feedback sections, safety flags.
- Unit: provider availability, dry-run command contract, missing-video Korean errors.
- Integration: plugin registration and result transform reviewer hook.
- Future: vendor API importer contract tests and PDF parser fixtures.
