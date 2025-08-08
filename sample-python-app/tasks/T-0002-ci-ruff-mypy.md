---
id: T-0002
title: Add ruff + mypy to CI
type: chore
priority: P2
depends_on: [T-0001]
status: queued
owner: unassigned
estimate: 2h
acceptance:
  - "CI runs ruff check and mypy; failures fail the job"
  - "PR template asks to confirm lint/type checks passed"
auto_policy: review_required
---

## Description
Enhance the CI pipeline by adding static analysis and type checking. Configure `ruff` for linting and `mypy` for type checks via `pyproject.toml`. Update the CI workflow to run these steps and fail on violations. Add a PR template checkbox to ensure contributors acknowledge running lint and type checks locally.

## Deliverables
- `pyproject.toml` (ruff and mypy configuration)
- Updated `.github/workflows/ci.yml` to run ruff and mypy
- `.github/PULL_REQUEST_TEMPLATE.md` with a checklist item for lint/type checks