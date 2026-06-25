# Media Cache Management Spec

## Problem
Generated PDFs, images, and documents need traceable paths and automatic cleanup.

## Scope
### In
- Generated gateway media is promoted under `cache/media/gateway_promoted/YYYYMMDD/`.
- Media cache cleanup covers `cache/media` and legacy `media_cache`.
- Cleanup is retention-based, safe-root guarded, and supports dry-run.
- A Miho cron script can run the cleanup daily.

### Out
- No migration of existing plugin-specific report folders.
- No deletion outside Miho media-cache roots.

## Acceptance Criteria
- New managed paths include category and UTC date.
- Old files beyond retention are deleted; fresh files are preserved.
- Dry-run reports candidates without deleting.
- Unsafe roots are rejected.
- Gateway media promotion keeps existing attachment behavior.

## Test Plan
- `tests/gateway/test_media_cache_manager.py`
- `tests/gateway/test_generated_media.py`
