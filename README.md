**Model picks (fast + accurate on your box):**

* **Developer:** `qwen3-coder:latest` — best bias toward code, great at diffs and small edits.
* **Reviewer:** `qwen3:32b` — steadier general reasoning than the coder variant; good for acceptance-criteria checking.
* **Planner / Taskmaster:** `qwen3:32b` — better structure + summarization than smaller models.
* **Boost (manual only, tricky PRs):** `gpt-oss:120b` — use sparingly; 8k ctx + slower, but can salvage gnarly logic.
* **Fallback / very fast checks:** `llama3.2:latest` — okay for tiny utility steps only.
* Skip for now: `deepseek-r1:14b` (verbose “reasoning” can bloat PR bodies) and the huge `qwen2.5vl:72b` (vision) for this workflow.

Default Ollama endpoint in the README is set to **`http://aether:11434`**.

---

````md
# Poor Man Codex Orchestrator (Python + Ollama)

FastAPI service that drives a simple LLM-style dev loop with **Taskmaster → Developer → PR → Reviewer → Integrator** against a target repo.  
Uses **Ollama** via **LiteLLM**, pointed at `http://aether:11434`.

---

## Features
- **Repo registry (multi-repo)**: manage multiple target repos with per-repo settings.
- **Modes**: `observe` (no changes), `pr` (open PRs), `disabled` (ignore).
- **Endpoints**: `/repos` (CRUD and summary), per-repo `/scan`, `/status`, `/work-next`.
- **Webhooks**: per-repo routing and signature verification.
- **Loop agents** (MVP): Taskmaster → Developer → Reviewer → Integrator.
- **Policy**: agents never push to `main`, only open PRs.

> Note: a background polling engine is coming next; webhooks already supported.

> Note: LLM calls are stubbed in MVP; the included flow is deterministic (no model needed to make the first CI PR). The README pre-wires Ollama for when you turn LLM steps on.

---

## Repos
You’ll have **two** repos:
1. **codex-orchestrator** (this service)
2. **sample-python-app** (target project the agents will work on)

---

## Requirements
- Python 3.11+
- Git installed and available on PATH
- A GitHub **Personal Access Token** (PAT) with `repo` scope (you can swap to a GitHub App later)
- **Ollama** host reachable at `http://aether:11434` with your models pulled

---

## Environment / Config

Create `.env` in `codex-orchestrator/`:

```env
# --- GitHub target repo (the app the agents will edit) ---
GH_TOKEN=ghp_your_token_here
GH_OWNER=your-gh-username-or-org
GH_REPO=sample-python-app
PROJECT_CLONE_URL=https://github.com/${GH_OWNER}/${GH_REPO}.git
DEFAULT_BRANCH=main

# --- Working dir for local clones ---
WORKDIR_ROOT=/tmp/codex-work

# --- Ollama via LiteLLM ---
# The orchestrator will use this when LLM steps are enabled
OLLAMA_BASE_URL=http://aether:11434

# Per-role model defaults (tune as you like)
LLM_PLANNER_MODEL=qwen3:32b
LLM_TASKMASTER_MODEL=qwen3:32b
LLM_DEVELOPER_MODEL=qwen3-coder:latest
LLM_REVIEWER_MODEL=qwen3:32b
LLM_INTEGRATOR_MODEL=none
````

> When you later enable LLM calls, the adapter reads `OLLAMA_BASE_URL` and `LLM_*_MODEL`.
> Stick to your local models: `qwen3-coder:latest`, `qwen3:32b`, `gpt-oss:20b`, `gpt-oss:120b`, etc.

---

## Install (orchestrator)

```bash
cd codex-orchestrator
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # or create your own as above
# edit .env with your GH + Ollama settings
uvicorn app.main:app --reload
```

Health check:

```bash
curl http://localhost:8000/health
```

---

## First run (no webhooks yet)

1. **Seed a task** (Taskmaster):

```bash
curl -X POST http://localhost:8000/run/taskmaster
```

2. **Open the first PR** (Developer):

```bash
curl -X POST http://localhost:8000/run/developer
```

This creates a branch like `feature/T-0001-initialize-basic-ci-for-python`, adds a minimal CI workflow + smoke test, and opens a PR.

3. **Merge the PR** in GitHub UI.

4. Integrator marks the seeded task `done` on merge (via the merge webhook, see below).
   If you haven’t wired webhooks yet, you can re-run Integrator by merging and then re-running Taskmaster/Developer on a new task.

---

## 5) Merge PR and verify task flips to done

Merge the PR in GitHub UI. The webhook triggers the Integrator, which opens a small **integration PR** that updates the matching `tasks/*.md` from `status: in_review` to `status: done`. Merge that integration PR to complete the loop.

## Hook up GitHub webhooks

On **sample-python-app** repo settings:

* Add a webhook:

  * **Payload URL**: `http://YOUR-ORCHESTRATOR-HOST:8000/webhook`
  * **Content type**: `application/json`
  * **Secret**: (optional for now)
  * **Events**: Check **Pull requests** (you can add more later)
  * **Active**: yes

With this, the **Reviewer** comments on `opened`/`synchronize` and the **Integrator** updates task files on `closed (merged)`.

---

## Project repo scaffold (sample-python-app)

Minimal set you should have:

```
sample-python-app/
  .github/
    workflows/
      ci.yml
    PULL_REQUEST_TEMPLATE.md
  docs/
    PRD.md
  tasks/
    _template.md
  tests/
    test_smoke.py
  src/
    __init__.py
    app.py
  CODEOWNERS
  .llm-team.yml
  requirements.txt
  README.md
```

Basic files (short versions):

* `.github/workflows/ci.yml`

  ```yaml
  name: CI
  on: [pull_request]
  jobs:
    test:
      runs-on: ubuntu-latest
      steps:
        - uses: actions/checkout@v4
        - uses: actions/setup-python@v5
          with: { python-version: '3.11' }
        - run: pip install -r requirements.txt || true
        - run: pytest -q || true
  ```

* `tasks/_template.md`

  ```md
  ---
  id: T-0000
  title: <title>
  type: feature|bugfix|doc|chore
  priority: P2
  depends_on: []
  status: queued
  owner: unassigned
  estimate: 2h
  acceptance:
    - "<acceptance 1>"
    - "<acceptance 2>"
  auto_policy: review_required
  ---
  ```

* `.llm-team.yml`

  ```yaml
  project:
    name: sample-python-app
    protected_paths: [".github/", "infra/", "secrets/"]
  workflow:
    branch_prefix: "feature/"
    merge_strategy: "squash"
    dry_run: false
  roles:
    planner: {enabled: true}
    taskmaster: {enabled: true}
    developer: {enabled: true}
    reviewer: {enabled: true}
    integrator: {enabled: true}
  tasks:
    dir: "tasks"
    states: ["queued","in_review","ready_for_integration","done","blocked"]
  checks:
    require_tests: true
    coverage_min: 0
  ```

---

## How the loop works (MVP)

* `POST /run/taskmaster` → creates `tasks/T-0001-ci-setup.md` if no queued tasks exist.
* `POST /run/developer` → creates a feature branch, writes CI + smoke test, flips task to `in_review`, opens PR.
* Webhook `pull_request`:

  * **opened/synchronize** → Reviewer posts a summary comment.
  * **closed (merged\:true)** → Integrator flips matching task to `done`.

All changes happen via PRs.

---

## Polling mode (NAT-friendly)

If you cannot expose webhooks, you can run the orchestrator in polling mode:

- Use `POST /poll/once` to poll all registered repos once. The response includes per-repo summaries, GitHub rate-limit info, and a suggested `next_interval`.
- The poller uses GitHub ETag caching (`If-None-Match`) to avoid counting against your budget when nothing changed (304 Not Modified).
- When a 200 response is returned, it reads `X-RateLimit-Remaining` and `X-RateLimit-Reset` and backs off automatically if the remaining budget is low.
- For open PRs, it triggers the Reviewer once per new head SHA. Periodically it also checks for recently merged PRs and triggers the Integrator.

Environment flags (optional): `POLLING_ENABLED`, `POLL_INTERVAL_ACTIVE`, `POLL_INTERVAL_IDLE`, `MIN_REMAINING_BUDGET`.

See also: `docs/CHANGELOG.md` for implementation details.

---

## Enabling LLM steps (when ready)

1. **Set your env** to point to Ollama:

   ```env
   OLLAMA_BASE_URL=http://aether:11434
   LLM_DEVELOPER_MODEL=qwen3-coder:latest
   LLM_REVIEWER_MODEL=qwen3:32b
   LLM_PLANNER_MODEL=qwen3:32b
   LLM_TASKMASTER_MODEL=qwen3:32b
   ```

2. **Use the adapter** in `app/adapters/llm_litellm.py` (already included).
   It calls LiteLLM’s `completion()` and reads `OLLAMA_BASE_URL`.
   When you start generating plans/diffs with the LLM, feed **acceptance criteria + minimal context/diffs**, not the whole repo.

3. **Temperatures**: keep Dev/Reviewer low (≤0.2), Planner a bit higher (≈0.5).

---

## Recommended models on your host

* **Primary (code):** `qwen3-coder:latest`
* **General reasoning:** `qwen3:32b`
* **Occasional boost:** `gpt-oss:120b` (manual use only)
* **Fast fallback:** `llama3.2:latest`
* **Embeddings (future):** `nomic-embed-text:latest`

> You reported \~26 t/s on 20B-class and \~18 t/s on 120B. That’s plenty for short tasks. Prefer 20B-class for routine work; reserve 120B for manual “boost” runs.

---

## Security & guardrails

* Use **CODEOWNERS** to require your review for `infra/`, `.github/`, `secrets/`, migrations.
* Agents **never** push to `main`.
* Keep tasks < 1 day with explicit acceptance criteria.

---

## Troubleshooting

* **PR didn’t open?** Check PAT scopes and that the branch pushed to origin.
* **No webhook actions?** Verify GitHub webhook deliveries → `pull_request` event → 2xx response.
* **Ollama calls fail?** Confirm `curl http://aether:11434/api/tags` works and models are pulled.

---

## Roadmap (next)

* Swap PAT → GitHub App (scoped, safer).
* Add ruff + mypy in CI and Reviewer.
* Queue (Redis/RQ) for backoff/idempotency.
* Turn on Planner/Taskmaster LLM generation of tasks from PRD.

