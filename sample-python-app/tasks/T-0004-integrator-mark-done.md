---
id: T-0004
title: Integrator marks task done on merge
type: feature
priority: P2
depends_on: [T-0003]
status: queued
owner: unassigned
estimate: 3h
acceptance:
  - "On pull_request closed: merged=true, matching task status flips to done"
  - "Commit message: '{T-####}: mark task done'"
auto_policy: review_required
---

## Description
Extend the webhook handling to react to `pull_request` events when a PR is closed and merged. Implement an integrator agent that locates the corresponding task by ID and updates its status to `done`. Ensure the merge commit message includes the required token format `{T-####}: mark task done`.

## Deliverables
- `codex-orchestrator/agents/integrator.py`
- Tests for status flip (optional)