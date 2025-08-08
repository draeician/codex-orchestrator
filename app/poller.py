from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from .registry import RepoContext
from .registry import STATE_DIR
from .adapters.vcs_github import VCS
from .agents.reviewer import Reviewer
from .agents.integrator import Integrator
from .config import load_settings


ETAG_DIR = STATE_DIR / "etags"


def _now_epoch() -> int:
    return int(time.time())


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _repo_state_path(repo_id: str) -> Path:
    return ETAG_DIR / f"{repo_id}.json"


def _load_repo_state(repo_id: str) -> Dict[str, Any]:
    path = _repo_state_path(repo_id)
    if not path.exists():
        return {}
    try:
        txt = path.read_text(encoding="utf-8")
        return json.loads(txt) if txt.strip() else {}
    except Exception:
        return {}


def _save_repo_state(repo_id: str, state: Dict[str, Any]) -> None:
    ETAG_DIR.mkdir(parents=True, exist_ok=True)
    path = _repo_state_path(repo_id)
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def load_etag(repo_id: str, key: str) -> Optional[str]:
    state = _load_repo_state(repo_id)
    return (state.get(key) or {}).get("etag")


def save_etag(repo_id: str, key: str, etag: Optional[str]) -> None:
    state = _load_repo_state(repo_id)
    bucket = dict(state.get(key) or {})
    if etag:
        bucket["etag"] = etag
    state[key] = bucket
    _save_repo_state(repo_id, state)


def _update_reviewed_heads(repo_id: str, heads: List[str]) -> None:
    state = _load_repo_state(repo_id)
    open_bucket = dict(state.get("open") or {})
    seen = set(open_bucket.get("reviewed_heads", []))
    for h in heads:
        seen.add(h)
    # Keep only recent up to 200
    open_bucket["reviewed_heads"] = list(list(seen))[-200:]
    state["open"] = open_bucket
    _save_repo_state(repo_id, state)


def _get_reviewed_heads(repo_id: str) -> set[str]:
    state = _load_repo_state(repo_id)
    return set((state.get("open") or {}).get("reviewed_heads", []))


def _get_cycle(repo_id: str) -> int:
    state = _load_repo_state(repo_id)
    return int(state.get("cycle", 0))


def _set_cycle(repo_id: str, value: int) -> None:
    state = _load_repo_state(repo_id)
    state["cycle"] = int(value)
    _save_repo_state(repo_id, state)


def _get_last_merged_seen(repo_id: str) -> Optional[str]:
    state = _load_repo_state(repo_id)
    return (state.get("closed") or {}).get("last_seen_merged_at")


def _set_last_merged_seen(repo_id: str, iso_ts: str) -> None:
    state = _load_repo_state(repo_id)
    closed_bucket = dict(state.get("closed") or {})
    closed_bucket["last_seen_merged_at"] = iso_ts
    state["closed"] = closed_bucket
    _save_repo_state(repo_id, state)


def compute_next_interval(remaining: Optional[int], reset_epoch: Optional[int], active: bool) -> int:
    settings = load_settings()
    # Backoff if close to budget
    if remaining is not None and remaining < int(settings.min_remaining_budget):
        now = _now_epoch()
        if reset_epoch and reset_epoch > now:
            # Backoff between 600 and 900 seconds or until reset
            wait = max(600, min(900, reset_epoch - now))
            return int(wait)
        return 600
    return int(settings.poll_interval_active if active else settings.poll_interval_idle)


def _parse_rate_headers(headers: httpx.Headers) -> Dict[str, Any]:
    remaining = headers.get("X-RateLimit-Remaining")
    reset = headers.get("X-RateLimit-Reset")
    etag = headers.get("ETag")
    try:
        remaining_i = int(remaining) if remaining is not None else None
    except ValueError:
        remaining_i = None
    try:
        reset_i = int(reset) if reset is not None else None
    except ValueError:
        reset_i = None
    return {"remaining": remaining_i, "reset": reset_i, "etag": etag}


def poll_repo(repo_ctx: RepoContext) -> Dict[str, Any]:
    settings = load_settings()
    vcs = VCS(repo_ctx, settings.gh_token)
    base_url = f"{vcs.base}/repos/{repo_ctx.owner}/{repo_ctx.repo}/pulls"

    reviewed = 0
    integrated = 0
    active = False

    # Open PRs polling
    open_key = "open"
    open_etag = load_etag(repo_ctx.id, open_key)
    headers = dict(vcs.headers)
    if open_etag:
        headers["If-None-Match"] = open_etag

    open_params = {"state": "open", "sort": "updated", "direction": "desc", "per_page": 10}
    with httpx.Client(timeout=30.0) as client:
        open_resp = client.get(base_url, headers=headers, params=open_params)

    open_rate = _parse_rate_headers(open_resp.headers)
    if open_resp.status_code == 200:
        prs: List[Dict[str, Any]] = open_resp.json()  # type: ignore[assignment]
        active = len(prs) > 0
        # Save new ETag
        save_etag(repo_ctx.id, open_key, open_rate.get("etag"))
        # Review idempotently by head SHA
        seen_heads = _get_reviewed_heads(repo_ctx.id)
        to_mark: List[str] = []
        for pr in prs:
            head = (pr.get("head") or {})
            head_ref = head.get("ref", "")
            head_sha = head.get("sha", "")
            if not head_sha or head_sha in seen_heads:
                continue
            payload = {"action": "synchronize", "pull_request": {**pr, "head": {"ref": head_ref, "sha": head_sha}}}
            Reviewer(repo_ctx).review_pull_request(payload)
            reviewed += 1
            to_mark.append(head_sha)
        if to_mark:
            _update_reviewed_heads(repo_ctx.id, to_mark)
    elif open_resp.status_code == 304:
        # Not modified; nothing to do
        pass
    else:
        # Non-success; return early with status
        return {
            "checked": True,
            "reviewed": 0,
            "integrated": 0,
            "status": f"error:{open_resp.status_code}",
            "next_interval": compute_next_interval(open_rate.get("remaining"), open_rate.get("reset"), active),
            "rate": open_rate,
        }

    # Closed PRs polling every Nth cycle
    cycle = _get_cycle(repo_ctx.id)
    next_cycle = (cycle + 1) % 3
    _set_cycle(repo_ctx.id, next_cycle)

    closed_rate: Dict[str, Any] = {}
    if cycle == 0:
        closed_key = "closed"
        closed_etag = load_etag(repo_ctx.id, closed_key)
        headers2 = dict(vcs.headers)
        if closed_etag:
            headers2["If-None-Match"] = closed_etag
        closed_params = {"state": "closed", "sort": "updated", "direction": "desc", "per_page": 10}
        with httpx.Client(timeout=30.0) as client:
            closed_resp = client.get(base_url, headers=headers2, params=closed_params)
        closed_rate = _parse_rate_headers(closed_resp.headers)
        if closed_resp.status_code == 200:
            pulls: List[Dict[str, Any]] = closed_resp.json()
            save_etag(repo_ctx.id, closed_key, closed_rate.get("etag"))
            last_seen = _get_last_merged_seen(repo_ctx.id)
            max_seen = last_seen
            for pr in pulls:
                merged_at = pr.get("merged_at")
                if not merged_at:
                    continue
                if last_seen and merged_at <= last_seen:
                    continue
                # Synthetic payload for Integrator
                payload = {"action": "closed", "pull_request": pr}
                Integrator(repo_ctx).on_merge(payload)
                integrated += 1
                if max_seen is None or merged_at > max_seen:
                    max_seen = merged_at
            if max_seen:
                _set_last_merged_seen(repo_ctx.id, max_seen)
        elif closed_resp.status_code == 304:
            pass
        else:
            # keep summary, but note error
            closed_rate["error"] = closed_resp.status_code

    # Compute next interval based on whichever latest rate info we have
    rate = open_rate or closed_rate or {}
    next_interval = compute_next_interval(rate.get("remaining"), rate.get("reset"), active)

    summary: Dict[str, Any] = {
        "checked": True,
        "reviewed": reviewed,
        "integrated": integrated,
        "status": "ok" if (reviewed or integrated) else "idle",
        "next_interval": next_interval,
        "rate": rate,
    }

    remaining = rate.get("remaining")
    reset_epoch = rate.get("reset")
    if isinstance(remaining, int) and remaining < int(load_settings().min_remaining_budget or 0):
        if isinstance(reset_epoch, int):
            summary["backoff_until"] = datetime.fromtimestamp(reset_epoch, tz=timezone.utc).isoformat()
    return summary
