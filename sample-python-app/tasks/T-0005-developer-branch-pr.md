---
id: T-0005
title: Developer branch/PR flow
type: feature
priority: P2
depends_on: [T-0003]
status: queued
owner: unassigned
estimate: 4h
acceptance:
  - "POST /run/developer creates feature/{task-id}-{slug} and opens a PR with template"
  - "Task status moves queued→in_review"
auto_policy: review_required
---

## Description
Provide an endpoint that kicks off a developer workflow for a task. When invoked, create a new branch named `feature/{task-id}-{slug}`, push it, and open a PR using a standard template. Update the task status from `queued` to `in_review` once the PR is opened successfully.

## Deliverables
- `codex-orchestrator/agents/developer.py`
- `codex-orchestrator/adapters/repo_git.py`
- `codex-orchestrator/adapters/vcs_github.py`