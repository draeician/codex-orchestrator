from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx

from .registry import RepoContext, STATE_DIR
from .agents.reviewer import Reviewer
from .agents.integrator import Integrator
from .config import load_settings


# ---- ETag state helpers ----

def _etag_path(repo_id: str) -> Path:
    etag_dir = STATE_DIR / "etags"
    etag_dir.mkdir(parents=True, exist_ok=True)
    return etag_dir / f"{repo_id}.json"


def _load_etags(repo_id: str) -> Dict[str, Any]:
    path = _etag_path(repo_id)
    if not path.exists():
        return {"open": {"etag": None, "seen": []}, "closed": {"etag": None, "last_merged_at": None}}
    try:
        raw = path.read_text(encoding="utf-8").strip()
        data = json.loads(raw) if raw else {}
    except Exception:
        data = {}
    # Ensure buckets exist
    open_b = data.get("open") or {}
    closed_b = data.get("closed") or {}
    data["open"] = {"etag": open_b.get("etag"), "seen": open_b.get("seen", [])}
    data["closed"] = {"etag": closed_b.get("etag"), "last_merged_at": closed_b.get("last_merged_at")}
    return data


def _save_etags(repo_id: str, data: Dict[str, Any]) -> None:
    path = _etag_path(repo_id)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


# ---- GitHub requests ----

def _gh_get(url: str, headers: Optional[Dict[str, str]] = None) -> Tuple[int, Dict[str, str], Any]:
    settings = load_settings()
    base_headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {settings.gh_token}",
        "User-Agent": "codex-orchestrator-poller",
    }
    if headers:
        base_headers.update(headers)
    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(url, headers=base_headers)
        status = resp.status_code
        # Convert headers to plain dict[str, str]
        hdrs: Dict[str, str] = {k: v for k, v in resp.headers.items()}
        try:
            data = resp.json() if status != 304 else None
        except Exception:
            data = None
        return status, hdrs, data
    except Exception as e:  # pragma: no cover
        # Network/transport error; surface as 0
        return 0, {}, {"error": str(e)}


# ---- Core ----

def poll_repo(repo_ctx: RepoContext) -> Dict[str, Any]:
    owner = repo_ctx.owner
    repo = repo_ctx.repo

    open_prs_url = (
        f"https://api.github.com/repos/{owner}/{repo}/pulls?state=open&sort=updated&direction=desc&per_page=10"
    )
    closed_prs_url = (
        f"https://api.github.com/repos/{owner}/{repo}/pulls?state=closed&sort=updated&direction=desc&per_page=10"
    )

    state = _load_etags(repo_ctx.id)

    open_changed: List[Dict[str, Any]] = []
    merged_changed: List[Dict[str, Any]] = []
    last_200_headers: Optional[Dict[str, str]] = None

    # ---- OPEN PRs pass ----
    open_headers: Dict[str, str] = {}
    open_etag = (state.get("open") or {}).get("etag")
    if open_etag:
        open_headers["If-None-Match"] = open_etag
    status, hdrs, data = _gh_get(open_prs_url, headers=open_headers)
    if status in {403, 404, 422, 0}:
        print(f"[poller] open PRs error for {repo_ctx.id}: status={status}")
        return {
            "repo": repo_ctx.id,
            "open_changed": [],
            "merged_changed": [],
            "rate_limit": {"remaining": None, "reset": None},
            "error": f"open:{status}",
        }
    if status == 200:
        last_200_headers = hdrs
        new_etag = hdrs.get("ETag")
        if new_etag:
            state.setdefault("open", {})["etag"] = new_etag
        open_changed = list(data or [])
    elif status == 304:
        open_changed = []

    # ---- CLOSED PRs pass ----
    closed_headers: Dict[str, str] = {}
    closed_etag = (state.get("closed") or {}).get("etag")
    if closed_etag:
        closed_headers["If-None-Match"] = closed_etag
    status2, hdrs2, data2 = _gh_get(closed_prs_url, headers=closed_headers)
    if status2 in {403, 404, 422, 0}:
        print(f"[poller] closed PRs error for {repo_ctx.id}: status={status2}")
        return {
            "repo": repo_ctx.id,
            "open_changed": [pr.get("number") for pr in open_changed],
            "merged_changed": [],
            "rate_limit": {"remaining": None, "reset": None},
            "error": f"closed:{status2}",
        }
    last_merged_at = (state.get("closed") or {}).get("last_merged_at")
    newest_merged_at: Optional[str] = last_merged_at
    if status2 == 200:
        last_200_headers = hdrs2  # the last 200 wins
        new_etag = hdrs2.get("ETag")
        if new_etag:
            state.setdefault("closed", {})["etag"] = new_etag
        pulls: List[Dict[str, Any]] = list(data2 or [])
        # Only consider merged PRs
        merged_prs = [pr for pr in pulls if pr.get("merged_at")]
        if last_merged_at is None:
            # First run: process only the most recent merged PR (avoid flooding)
            merged_prs = merged_prs[:1]
        for pr in merged_prs:
            merged_at = pr.get("merged_at")
            if last_merged_at and merged_at <= last_merged_at:
                continue
            merged_changed.append(pr)
            if newest_merged_at is None or merged_at > newest_merged_at:
                newest_merged_at = merged_at
        if newest_merged_at:
            state.setdefault("closed", {})["last_merged_at"] = newest_merged_at
    elif status2 == 304:
        pass

    # ---- Rate limit ----
    remaining: Optional[int] = None
    reset_epoch: Optional[int] = None
    if last_200_headers is not None:
        try:
            remaining = int(last_200_headers.get("X-RateLimit-Remaining", ""))
        except Exception:
            remaining = None
        try:
            reset_epoch = int(last_200_headers.get("X-RateLimit-Reset", ""))
        except Exception:
            reset_epoch = None

    # ---- Actions ----
    repo_full_name = f"{owner}/{repo}"
    open_numbers: List[int] = []
    for pr in open_changed:
        try:
            payload = {
                "action": "synchronize",
                "pull_request": {
                    "number": pr.get("number"),
                    "title": pr.get("title"),
                    "head": {"ref": pr.get("head", {}).get("ref"), "sha": pr.get("head", {}).get("sha")},
                    "base": {"ref": pr.get("base", {}).get("ref")},
                },
                "repository": {"full_name": repo_full_name},
            }
            Reviewer(repo_ctx).review_pull_request(payload)
            if pr.get("number") is not None:
                open_numbers.append(int(pr["number"]))
        except Exception as e:  # pragma: no cover
            print(f"[poller] reviewer error for {repo_ctx.id} PR#{pr.get('number')}: {e}")

    merged_numbers: List[int] = []
    for pr in merged_changed:
        try:
            payload = {
                "action": "closed",
                "pull_request": {
                    "number": pr.get("number"),
                    "title": pr.get("title"),
                    "merged": True,
                    "merge_commit_sha": pr.get("merge_commit_sha"),
                },
                "repository": {"full_name": repo_full_name},
            }
            Integrator(repo_ctx).on_merge(payload)
            if pr.get("number") is not None:
                merged_numbers.append(int(pr["number"]))
        except Exception as e:  # pragma: no cover
            print(f"[poller] integrator error for {repo_ctx.id} PR#{pr.get('number')}: {e}")

    # ---- Save and summarize ----
    _save_etags(repo_ctx.id, state)

    summary: Dict[str, Any] = {
        "repo": repo_ctx.id,
        "open_changed": open_numbers,
        "merged_changed": merged_numbers,
        "rate_limit": {"remaining": remaining, "reset": reset_epoch},
    }
    # Include additional closed summary info
    try:
        summary["closed_seen"] = len(merged_changed)
    except Exception:
        pass
    if remaining is not None and remaining < 200 and reset_epoch:
        summary["backoff_until"] = datetime.fromtimestamp(reset_epoch, tz=timezone.utc).isoformat()
    return summary
