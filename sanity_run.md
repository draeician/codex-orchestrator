
# 0) Prep

* Orchestrator running:

```bash
uvicorn app.main:app --reload
```

* `.env` set with a valid `GH_TOKEN` and `OLLAMA_BASE_URL=http://aether:11434`.
* Pick a target repo you own (or your `sample-python-app`). I’ll call it:

  * **owner** = `YOUR_GH_USER`
  * **repo**  = `sample-python-app`
  * **repo\_id** = `YOUR_GH_USER_sample-python-app`

---

# 1) Register the repo (defaults to observe mode)

```bash
curl -sX POST http://localhost:8000/repos \
  -H 'Content-Type: application/json' \
  -d '{
    "owner":"YOUR_GH_USER",
    "repo":"sample-python-app",
    "default_branch":"main",
    "mode":"observe"
  }' | jq
```

List to confirm:

```bash
curl -s http://localhost:8000/repos | jq
```

Expected: entry with `"id":"YOUR_GH_USER_sample-python-app"` and `"mode":"observe"`.

---

# 2) Wire the webhook (PR events)

In the **GitHub repo settings → Webhooks**:

* Payload URL: `http://YOUR_ORCH_HOST:8000/webhook`
* Content type: `application/json`
* Secret: *(optional; if you set `webhook_secret` later in PATCH, add it here too)*
* Events: **Pull requests**
* Active: ✅

*(You can set/rotate the per-repo secret later via PATCH; for now it can be empty.)*

---

# 3) First scan + status (observe mode)

```bash
curl -sX POST http://localhost:8000/repos/YOUR_GH_USER_sample-python-app/scan | jq
curl -s    http://localhost:8000/repos/YOUR_GH_USER_sample-python-app/status | jq
```

Expected: a “present” summary, plus either a `next_task` (e.g., T-0001) or `null`.

---

# 4) Try work in observe mode (should do nothing)

```bash
curl -sX POST http://localhost:8000/repos/YOUR_GH_USER_sample-python-app/work-next | jq
```

Expected: JSON with `mode: "observe"` and a message like “No changes performed in observe mode.”

---

# 5) Bootstrap (if missing scaffolding)

Preview plan (still observe):

```bash
curl -sX POST http://localhost:8000/repos/YOUR_GH_USER_sample-python-app/bootstrap | jq
```

* If it returns `204` “nothing to bootstrap”, skip to step 6.
* If it returns a list of file ops, flip to **pr** and run it again to open the bootstrap PR:

```bash
curl -sX POST http://localhost:8000/repos/YOUR_GH_USER_sample-python-app/set-mode \
  -H 'Content-Type: application/json' -d '{"mode":"pr"}' | jq

curl -sX POST http://localhost:8000/repos/YOUR_GH_USER_sample-python-app/bootstrap | jq
```

Go to GitHub, review & **merge** the bootstrap PR.

Re-scan:

```bash
curl -sX POST http://localhost:8000/repos/YOUR_GH_USER_sample-python-app/rescan | jq
```

---

# 6) Work the next task (pr mode)

Kick it:

```bash
curl -sX POST http://localhost:8000/repos/YOUR_GH_USER_sample-python-app/work-next | jq
```

Expected:

* Returns `{ ok:true, task:"T-0001", branch:"feature/T-0001-...", pr_url:"..." }`
* A new PR appears on GitHub (CI + smoke test; PR body links `docs/CHANGELOG.md`)
* **Webhook check:** The Reviewer agent should comment automatically on the PR.

Merge the feature PR in GitHub.

---

# 7) Integrator “mark-done” PR

After you merge the feature PR:

* The webhook triggers the Integrator to open a **tiny** PR that flips the task file to `status: done`.

Merge that integration PR.

Validate there’s no more work:

```bash
curl -s http://localhost:8000/repos/YOUR_GH_USER_sample-python-app/next-task | jq
curl -sX POST http://localhost:8000/repos/YOUR_GH_USER_sample-python-app/work-next -i
```

Expected:

* `next-task` → `null`
* `work-next` → HTTP **204** “no work”

---

# 8) Idempotency / lock check

Fire two work requests quickly:

```bash
( curl -sX POST http://localhost:8000/repos/YOUR_GH_USER_sample-python-app/work-next & \
  curl -sX POST http://localhost:8000/repos/YOUR_GH_USER_sample-python-app/work-next ) | cat
```

Expected: one succeeds (opens/returns PR URL), the other returns HTTP **423** “repo busy”.

---

# 9) Optional: set a webhook secret

Set per-repo secret (then also set the same secret in GitHub’s webhook):

```bash
curl -sX PATCH http://localhost:8000/repos/YOUR_GH_USER_sample-python-app \
  -H 'Content-Type: application/json' \
  -d '{"webhook_secret":"change_me"}' | jq
```

Re-open a PR or push to an existing PR branch to confirm webhooks still work (Reviewer comments).

---

# 10) Optional: add a second repo (stays idle)

Register another repo you own (leave in **observe**):

```bash
curl -sX POST http://localhost:8000/repos \
  -H 'Content-Type: application/json' \
  -d '{"owner":"YOUR_GH_USER","repo":"another-repo","default_branch":"main","mode":"observe"}' | jq
curl -s http://localhost:8000/repos | jq
```

* Verify it scans, reports `next_task` or `null`, and **does nothing** when you call `/work-next` (observe mode).

---

# What to look for in PRs

* **PR title**: includes the task id (e.g., `T-0001 - Initialize basic CI for Python`).
* **PR body**: Acceptance criteria section + **Documentation** section linking `docs/CHANGELOG.md`.
* **Diff**: minimal changes to satisfy acceptance; `tasks/T-0001...` flipped to `in_review` in the PR branch.
* **Reviewer comment**: checklist referencing CI + docs update.
* **Follow-up PR** (Integrator): single-line change `in_review → done`.
