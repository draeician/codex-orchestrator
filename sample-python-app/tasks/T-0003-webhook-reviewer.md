---
id: T-0003
title: Webhook router and PR Reviewer comment
type: feature
priority: P2
depends_on: [T-0001, T-0002]
status: queued
owner: unassigned
estimate: 4h
acceptance:
  - "FastAPI /webhook endpoint handles GitHub pull_request opened/synchronize"
  - "Automated comment includes CI summary + acceptance checklist link"
auto_policy: review_required
---

## Description
Introduce a webhook handler using FastAPI that accepts GitHub webhook events. Specifically support `pull_request` events for the `opened` and `synchronize` actions. Implement a reviewer agent that posts an automated comment on the PR summarizing the latest CI status and linking to the task acceptance checklist.

## Deliverables
- `codex-orchestrator/app/main.py`
- `codex-orchestrator/app/router.py`
- `codex-orchestrator/agents/reviewer.py`