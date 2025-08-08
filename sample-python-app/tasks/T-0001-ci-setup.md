---
id: T-0001
title: Initialize basic CI for Python
type: chore
priority: P2
depends_on: []
status: queued
owner: unassigned
estimate: 2h
acceptance:
  - "On pull_request, GitHub Actions runs pytest and reports status"
  - "A minimal tests/test_smoke.py exists and passes"
auto_policy: review_required
---

## Description
Set up a minimal continuous integration workflow for a Python project. The workflow should trigger on pull requests, install dependencies, and run pytest. Include a basic smoke test to validate the CI is wired correctly and passes.

## Deliverables
- `.github/workflows/ci.yml`
- `tests/test_smoke.py`