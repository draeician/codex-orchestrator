# PRD: Sample Python App

## Goal
Provide a trivial Python package with CI and a smoke test so the orchestrator loop can operate.

## Milestones
1. CI bootstrap for pytest on pull_request.
2. Add linting (ruff) and type checks (mypy).  [future]
3. Simple feature endpoint and unit tests.        [future]

## Acceptance
- On any pull_request, GitHub Actions runs pytest and reports a status.
- A minimal test exists and passes.

