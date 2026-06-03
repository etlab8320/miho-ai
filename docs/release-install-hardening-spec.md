# Release Install Hardening Spec

## Problem
Miho release installs must behave the same across macOS, Linux, WSL, and native Windows. A dev checkout using `.venv` and a release checkout using `venv` must not drift in update, gateway service, or local embedding behavior.

## Users And Jobs
- End users need one installer/update path that does not require Python packaging knowledge.
- Operators need gateway services to start after install/update with the same tool PATH as interactive runs.
- Keyless installs need the local e5 embedding fallback available by default.

## Scope
### In
- Shared virtualenv discovery for update and gateway service paths.
- Release installer contracts for `[all]`, `local-embeddings`, and e5 prefetch.
- Token-based messaging SDK repair before a freshly installed gateway starts.
- Tests for macOS/Linux-style `.venv` and `venv`, plus Windows `venv\Scripts`.

### Out
- Full rewrite of the large installer scripts.
- Real native Windows VM execution from this macOS workspace.
- Production server restart without an explicit deployment step.

## Acceptance Criteria
- `miho update` reinstalls into the detected project venv, not a hardcoded `venv`.
- Gateway service PATH includes detected `.venv/bin` or `venv/bin`.
- Standalone `scripts/miho-gateway` uses the same venv priority.
- Release `[all]` includes `local-embeddings`.
- Bash and PowerShell installers both keep e5 prefetch and `MIHO_SKIP_MODEL_PREFETCH`.
- Bash and PowerShell installers use locked messaging SDK specs when tokens are configured.
- Focused release/update/gateway tests pass with the project test wrapper.

## Test Plan
- Add unit tests for shared venv discovery.
- Add update reinstall tests that inspect `VIRTUAL_ENV`.
- Add release contract tests for local embeddings and installer prefetch.
- Run gateway, Windows gateway, update, release, and ACP version-lockstep tests.

## Risks
- `miho_cli/main.py` and `miho_cli/gateway.py` are existing oversized files. This work may touch small adapter points there, but full splitting is a later refactor.
