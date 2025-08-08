# PRD: Poor Man Codex Orchestrator

**Version:** 1.0
**Date:** 2025-08-07
**Owner:** Draeician
**Status:** Draft → Target “M1” sign-off

---

## 1) Summary

Build a lightweight, self-hosted system that uses local LLMs (Ollama) to simulate a software dev team workflow (**Planner → Taskmaster → Developer → Reviewer → Integrator**) operating on a target Git repository. The MVP delivers a deterministic end-to-end loop with optional LLM augmentation, gated by PR reviews and CI. The system must be cheap to run, auditable, and safe by default.

---

## 2) Goals & Non-Goals

### 2.1 Goals

* Provide a **repeatable workflow** that converts tasks into small, reviewable PRs.
* Use **Ollama** at `http://aether:11434` for local inference; no paid APIs.
* Keep **agents read/write actions auditable** via Git commits and PR comments; never push to `main` directly.
* Ensure **minimal setup**: two repos (orchestrator + project), one webhook, a PAT (upgradeable to GitHub App later).
* Deliver **deterministic MVP** (no LLM dependence) with toggles to enable LLM planning and review when desired.

### 2.2 Non-Goals (MVP)

* Multi-repo orchestration and cross-service dependency graphs.
* Complex natural-language planning across large codebases.
* Automatic database migrations, infrastructure changes, or secret management.
* Vision inputs or embeddings/RAG (can be added later).

---

## 3) Users & Use Cases

* **Primary user:** Draeician (maintainer/operator).
* **Use cases:**

  1. Seed/maintain a task backlog from a PRD.
  2. Turn a queued task into a small PR with CI and smoke tests.
  3. Auto-review PRs for checklists and simple static signals; require human approval by policy.
  4. On merge, mark the corresponding task “done” and log the change.

---

## 4) System Context

* **Repos**

  * `codex-orchestrator` (FastAPI service + agents + adapters)
  * `sample-python-app` (target project repo)
* **Event Flow (MVP)**

  * Taskmaster seeds `tasks/T-*.md` from PRD (seed task provided).
  * Developer claims first `queued` task, creates feature branch, edits files, opens PR.
  * Reviewer comments summary on PR `opened/synchronize`.
  * Human approves; Integrator updates task status on `merged:true`.

---

## 5) Functional Requirements

### 5.1 Roles & Behaviors

* **Planner (toggleable)**

  * Reads `docs/PRD.md`, emits milestones and task hints (M2+).
* **Taskmaster (required)**

  * Creates/updates Markdown tasks under `/tasks/`, one task ≤ 1 day, each with acceptance criteria.
  * Won’t duplicate queued tasks.
* **Developer (required)**

  * Claims first `status: queued`, creates `feature/{task-id}-{slug}`, applies minimal changes to meet acceptance criteria, marks task `in_review`, opens PR with template.
* **Reviewer (required)**

  * On PR `opened/synchronize`, posts an automated checklist comment (CI results, acceptance link, risk).
  * Never merges; cannot bypass CODEOWNERS.
* **Integrator (required)**

  * On PR `closed (merged:true)`, flips task `in_review → done` with a commit “{T-####}: mark task done”.

### 5.2 Task Spec (YAML front-matter + body)

* Fields: `id`, `title`, `type`, `priority`, `depends_on`, `status`, `owner`, `estimate`, `acceptance[]`, `auto_policy`.
* States: `queued` → `in_review` → `ready_for_integration` (manual tick) → `done` (auto on merge) → `blocked` (manual).

### 5.3 Branching & PR

* Branch name: `feature/{task-id}-{kebab-title}`.
* PR template includes: Linked Task ID, What Changed, Validation, Risk.
* Merge strategy: **Squash**.

### 5.4 Webhooks & Endpoints

* Webhook: `pull_request` → `POST /webhook`.
* Manual kicks:

  * `POST /run/taskmaster` (seed/update tasks)
  * `POST /run/developer` (work next task)
  * (M2) `POST /run/planner`, `POST /run/reviewer?pr=<num>`

### 5.5 Configuration

* `.env` in orchestrator:

  * `GH_TOKEN`, `GH_OWNER`, `GH_REPO`, `PROJECT_CLONE_URL`, `DEFAULT_BRANCH`, `WORKDIR_ROOT`
  * `OLLAMA_BASE_URL=http://aether:11434`
  * `LLM_PLANNER_MODEL`, `LLM_TASKMASTER_MODEL`, `LLM_DEVELOPER_MODEL`, `LLM_REVIEWER_MODEL`, `LLM_INTEGRATOR_MODEL`
* Project `.llm-team.yml`:

  * Protected paths (`.github/`, `infra/`, `secrets/`)
  * Branch prefix, merge strategy, dry-run toggle
  * Task dir and states
  * Checks thresholds (coverage, etc.)

### 5.6 CI Requirements (MVP)

* GitHub Actions workflow that runs `pytest` on `pull_request`.
* Future: add `ruff`, `mypy`, and coverage gate.

---

## 6) Non-Functional Requirements

### 6.1 Performance

* **Local models & speeds:**

  * Prefer 20B-class models for routine steps; target < 3s planning prompts.
  * 120B allowed for manual “boost” only; keep prompts short (≤ 1.5k tokens).
* **Token budgets:**

  * Dev/Review prompts ≤ 400 input tokens, ≤ 300 output tokens.
  * Planner ≤ 1.5k/1k (only when enabled).
* Keep deterministic MVP path independent of LLM availability.

### 6.2 Reliability & Idempotency

* Agents must be **idempotent** for re-delivered webhooks.
* No direct writes to `main`. All changes PR-gated.

### 6.3 Security

* **CODEOWNERS** required review for `.github/`, `infra/`, `secrets/`, and DB migrations.
* PAT stored only in orchestrator env; migrate to GitHub App (M2).

### 6.4 Observability

* Agent actions logged to console + simple JSON in `state/`.
* (M2) Structured logs with task/PR correlation IDs.

---

## 7) Model Strategy (Ollama @ aether:11434)

* **Developer (default):** `qwen3-coder:latest`
  Rationale: strong code edits and diff discipline.
* **Reviewer / Taskmaster / Planner:** `qwen3:32b`
  Rationale: better summarization and spec alignment than smaller Llama.
* **Manual boost (rare):** `gpt-oss:120b`
  Rationale: deeper reasoning for hairy cases; 8k ctx; higher latency.
* **Fast fallback:** `llama3.2:latest`
  Rationale: quick utility steps, not primary.

Temperatures: Dev/Review 0.1–0.2; Planner/Taskmaster 0.3–0.5.
Context discipline: pass **acceptance criteria + minimal diffs**, not whole repo.

---

## 8) Deliverables

1. **Orchestrator repo** with:

   * FastAPI service, agents, adapters, prompts, `.env.example`, `requirements.txt`, `README.md`.
2. **Project repo scaffold** with:

   * `docs/PRD.md`, `tasks/_template.md`, `.llm-team.yml`, CI workflow, PR template, CODEOWNERS, `tests/test_smoke.py`.

---

## 9) Milestones & Acceptance Criteria

### M0 — Skeleton (Day 1)

**Scope:** Repo scaffolds, env config, health endpoint.
**Acceptance:**

* Orchestrator boots (`/health` returns `ok: true`).
* Project repo contains CI, template, and task template.

### M1 — Deterministic E2E Loop (Day 1–2)

**Scope:** Taskmaster → Developer → PR → Reviewer (comment) → Integrator (on merge). No LLM required.
**Acceptance:**

* `POST /run/taskmaster` creates `tasks/T-0001-ci-setup.md` if none queued.
* `POST /run/developer` opens a PR with CI + smoke test and sets task `in_review`.
* Webhook `pull_request` → Reviewer comment appears.
* On merge, Integrator commits `status: done` for `T-0001`.

### M2 — LLM Augmentation (Day 3–5)

**Scope:** Enable LLM planning and micro-diff proposals.
**Acceptance:**

* Env points to `OLLAMA_BASE_URL=http://aether:11434`.
* Developer can ask LLM to produce a 3–5 line change plan and PR body rationale.
* Taskmaster can propose ≤ 5 new tasks from PRD diffs (behind a `dry_run` toggle).
* ruff + mypy added to CI; Reviewer comment summarizes their outcomes.

### M3 — Safety & UX (Week 2)

**Scope:** GitHub App auth, retries/backoff, richer logs.
**Acceptance:**

* GitHub App replaces PAT; least-privilege scopes.
* Replayed webhooks don’t create duplicate tasks or PRs.
* JSON action logs written with correlation IDs; simple dashboard page shows last 50 actions.

---

## 10) Risks & Mitigations

* **LLM drift / noisy output** → Keep deterministic path; strict prompts; low temperature; short contexts.
* **Repo corruption** → PR-only writes; branch protections; CODEOWNERS; human approval required.
* **Webhook retries** → Idempotent checks; task/PR existence checks by ID.
* **Performance on large repos** → Operate on **diff hunks** and acceptance criteria; avoid full-repo prompts.

---

## 11) Open Questions

1. Do we mirror `/tasks` to GitHub Issues or keep `/tasks` canonical only?
2. Minimum bar for CI at M2: enforce ruff/mypy failures or just warn?
3. Add `ready_for_integration` as a manual label or file toggle before Integrator acts?
4. Do we want Redis from day one for a background queue, or start sync and add later?

---

## 12) Appendix

### 12.1 Project Repo Structure (reference)

```
project/
  docs/PRD.md
  tasks/_template.md
  .llm-team.yml
  .github/
    workflows/ci.yml
    PULL_REQUEST_TEMPLATE.md
  CODEOWNERS
  tests/test_smoke.py
  src/
    __init__.py
    app.py
```

### 12.2 Orchestrator Endpoints (MVP)

* `GET /health` → `{ ok: true }`
* `POST /webhook` (GitHub `pull_request`)
* `POST /run/taskmaster`
* `POST /run/developer`

### 12.3 Default Prompting Rules (when LLM enabled)

* Preload acceptance criteria + target files only.
* Ask for **minimal viable edit plan** and short PR body.
* Reject plans that touch protected paths; request human ack.

