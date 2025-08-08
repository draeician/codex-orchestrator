# Dev smoke test

Follow these steps to run an end-to-end smoke of the orchestrator against your `sample-python-app` repo.

## 1) Start the API server

```bash
uvicorn app.main:app --reload
```

Health check:

```bash
curl http://localhost:8000/health
# {"ok": true}
```

## 2) Seed the first task (Taskmaster)

```bash
curl -X POST http://localhost:8000/run/taskmaster
```

## 3) Open the first PR (Developer)

```bash
curl -X POST http://localhost:8000/run/developer
```

This should:
- Create a branch like `feature/T-0001-initialize-basic-ci-for-python`
- Add `.github/workflows/ci.yml` and `tests/test_smoke.py`
- Open a PR on GitHub

## 4) Configure GitHub webhook

On the `sample-python-app` repository, add a webhook:
- Payload URL: `http://YOUR-HOST:8000/webhook`
- Content type: `application/json`
- Events: check `Pull requests`
- Active: true

## 5) Merge PR and verify task flips to done

Merge the PR in GitHub UI. The webhook will trigger the Integrator:
- It finds the task id from the PR title
- Updates the matching `tasks/*.md` file: `status: in_review` → `status: done`
- Commits the change (integration branch + PR)

Re-run Developer to pick up the next task when ready.
