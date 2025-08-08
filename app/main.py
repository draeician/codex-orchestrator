from typing import Optional, List, Dict, Any

from fastapi import FastAPI, Request, HTTPException, Response
from pydantic import BaseModel, Field

from .router import handle_pr_event, run_taskmaster, run_developer
from .registry import (
    RepoContext,
    RepoMode,
    list_repos,
    get_repo,
    upsert_repo,
    patch_repo,
)
from .config import load_settings
from .scan import scan_repo, load_tasks
from .locks import acquire as acquire_lock, release as release_lock
from .agents.developer import Developer
from .adapters.repo_git import RepoHelper
from .security import verify_signature
from .agents.reviewer import Reviewer
from .agents.integrator import Integrator
from .bootstrap import compute_bootstrap_plan, apply_bootstrap

app = FastAPI(title="Poor Man Codex Orchestrator", version="0.1.0")

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/webhook")
async def webhook(request: Request):
    # Read raw body once to both verify signature and parse JSON
    raw = await request.body()
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid json payload")

    event = request.headers.get("X-GitHub-Event", "")

    # Map to repo context based on repository.full_name
    repo = (payload.get("repository") or {})
    full_name = repo.get("full_name") or ""
    if "/" in full_name:
        owner, repo_name = full_name.split("/", 1)
        repo_id = f"{owner}_{repo_name}"
    else:
        repo_id = ""

    rc = get_repo(repo_id) if repo_id else None
    if rc is None:
        # Unknown repo -> accept but ignore
        return {"received": True, "event": event, "ignored": True}

    # Verify signature when configured
    try:
        verify_signature(request, rc.webhook_secret or "", raw)
    except HTTPException as e:
        # Return same error
        raise e

    if event == "pull_request":
        action = (payload.get("action") or "").lower()
        if action in {"opened", "synchronize"}:
            Reviewer(rc).review_pull_request(payload)
        elif action == "closed" and (payload.get("pull_request", {}).get("merged") is True):
            Integrator(rc).on_merge(payload)
    return {"received": True, "event": event}

@app.post("/run/taskmaster")
def run_taskmaster_endpoint():
    return run_taskmaster()

@app.post("/run/developer")
def run_developer_endpoint():
    return run_developer()


# ---- Repo registry endpoints ----

class RepoCreate(BaseModel):
    owner: str
    repo: str
    clone_url: Optional[str] = None
    default_branch: Optional[str] = Field(default="main")
    mode: Optional[str] = Field(default="observe")


class RepoPatch(BaseModel):
    mode: Optional[str] = None
    target_subdir: Optional[str] = None
    webhook_secret: Optional[str] = None


@app.post("/repos")
def create_repo(body: RepoCreate):
    ctx = RepoContext.from_partial(
        owner=body.owner,
        repo=body.repo,
        clone_url=body.clone_url,
        default_branch=body.default_branch,
        mode=body.mode,
    )
    saved = upsert_repo(ctx)
    return saved.to_dict()


@app.get("/repos")
def list_repos_endpoint():
    settings = load_settings()
    summaries: List[Dict[str, Any]] = []
    for rc in list_repos():
        report = scan_repo(rc, settings.workdir_root, settings.gh_token)
        summaries.append(
            {
                "id": rc.id,
                "mode": rc.mode.value,
                "default_branch": rc.default_branch,
                "next_task": report.get("next_task"),
                "open_pr_count": len(report.get("open_prs", [])),
            }
        )
    return summaries


@app.get("/repos/{repo_id}")
def get_repo_endpoint(repo_id: str):
    rc = get_repo(repo_id)
    if rc is None:
        raise HTTPException(status_code=404, detail="repo not found")
    return rc.to_dict()


@app.patch("/repos/{repo_id}")
def patch_repo_endpoint(repo_id: str, body: RepoPatch):
    # Validate mode if present
    fields = body.dict(exclude_unset=True)
    if "mode" in fields and fields["mode"] is not None:
        # Validate mode value
        try:
            RepoMode(fields["mode"])  # type: ignore[arg-type]
        except ValueError:
            raise HTTPException(status_code=400, detail="invalid mode")
    updated = patch_repo(repo_id, **fields)
    return updated.to_dict()


class ModeSet(BaseModel):
    mode: str


@app.post("/repos/{repo_id}/set-mode")
def set_mode_endpoint(repo_id: str, body: ModeSet):
    # Validate mode
    try:
        RepoMode(body.mode)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid mode")
    updated = patch_repo(repo_id, mode=body.mode)
    return updated.to_dict()


# ---- Repo scan/status endpoints ----

@app.post("/repos/{repo_id}/scan")
def scan_repo_endpoint(repo_id: str):
    rc = get_repo(repo_id)
    if rc is None:
        raise HTTPException(status_code=404, detail="repo not found")
    settings = load_settings()
    report = scan_repo(rc, settings.workdir_root, settings.gh_token)
    return {**report, "mode": rc.mode.value}


@app.get("/repos/{repo_id}/status")
def repo_status_endpoint(repo_id: str):
    rc = get_repo(repo_id)
    if rc is None:
        raise HTTPException(status_code=404, detail="repo not found")
    settings = load_settings()
    report = scan_repo(rc, settings.workdir_root, settings.gh_token)
    # Include current repo mode for convenience
    report_with_mode = {**report, "mode": rc.mode.value}
    return report_with_mode


@app.post("/repos/{repo_id}/rescan")
def repo_rescan_endpoint(repo_id: str):
    rc = get_repo(repo_id)
    if rc is None:
        raise HTTPException(status_code=404, detail="repo not found")
    settings = load_settings()
    report = scan_repo(rc, settings.workdir_root, settings.gh_token)
    return {**report, "mode": rc.mode.value}


@app.post("/repos/{repo_id}/work-next")
def work_next_endpoint(repo_id: str):
    rc = get_repo(repo_id)
    if rc is None:
        raise HTTPException(status_code=404, detail="repo not found")

    settings = load_settings()

    # If in observe mode, suggest next task but do not proceed
    if rc.mode == RepoMode.observe:
        report = scan_repo(rc, settings.workdir_root, settings.gh_token)
        return {
            "mode": rc.mode.value,
            "next_task": report.get("next_task"),
            "message": "No changes performed in observe mode",
        }

    # Acquire lock to ensure single worker per repo
    if not acquire_lock(repo_id, settings.workdir_root, timeout=0):
        raise HTTPException(status_code=423, detail="repo busy")

    try:
        # Scan for next eligible task
        report = scan_repo(rc, settings.workdir_root, settings.gh_token)
        next_task_min = report.get("next_task")
        if not next_task_min:
            return Response(status_code=204)

        # Load full task dict for the chosen id
        repo = RepoHelper(rc, settings.workdir_root)
        repo_root = repo.ensure_local_clone()
        tasks = load_tasks(repo_root)
        task_full = None
        for t in tasks:
            if t.get("id") == next_task_min.get("id"):
                task_full = t
                break
        if task_full is None:
            return Response(status_code=204)

        dev = Developer(rc)
        result = dev.work_task(task_full)  # to be implemented by Developer

        if not result or not result.get("ok"):
            raise HTTPException(status_code=500, detail={"message": "developer failed", "result": result})

        return {
            "task": task_full.get("id"),
            "branch": result.get("branch"),
            "pr_url": result.get("pr_url"),
        }
    finally:
        release_lock(repo_id, settings.workdir_root)


@app.get("/repos/{repo_id}/next-task")
def next_task_endpoint(repo_id: str):
    rc = get_repo(repo_id)
    if rc is None:
        raise HTTPException(status_code=404, detail="repo not found")
    settings = load_settings()
    report = scan_repo(rc, settings.workdir_root, settings.gh_token)
    return {"next_task": report.get("next_task")}


@app.post("/repos/{repo_id}/bootstrap")
def bootstrap_endpoint(repo_id: str):
    rc = get_repo(repo_id)
    if rc is None:
        raise HTTPException(status_code=404, detail="repo not found")
    settings = load_settings()

    # Compute current state and plan
    helper = RepoHelper(rc, settings.workdir_root)
    repo_root = helper.ensure_local_clone()
    plan = compute_bootstrap_plan(repo_root)
    if not plan:
        return Response(status_code=204)

    if rc.mode == RepoMode.observe:
        return {"mode": rc.mode.value, "plan": plan, "message": "Preview only in observe mode"}

    # PR mode: apply and open PR
    result = apply_bootstrap(rc, plan)
    return result

