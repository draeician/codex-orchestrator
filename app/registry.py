from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional, List, Dict, Any

STATE_DIR = Path(os.getenv("STATE_DIR", Path(__file__).resolve().parents[1] / "state"))
REGISTRY_PATH = STATE_DIR / "registry.json"


class RepoMode(str, Enum):
    observe = "observe"
    pr = "pr"
    disabled = "disabled"


@dataclass
class RepoContext:
    id: str
    owner: str
    repo: str
    clone_url: str
    default_branch: str = "main"
    mode: RepoMode = RepoMode.observe
    target_subdir: Optional[str] = None
    webhook_secret: Optional[str] = ""
    protected_paths: List[str] = field(default_factory=lambda: [".github/", "infra/", "secrets/"])
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @staticmethod
    def derive_id(owner: str, repo: str) -> str:
        return f"{owner}_{repo}"

    @staticmethod
    def build_clone_url(owner: str, repo: str) -> str:
        return f"https://github.com/{owner}/{repo}.git"

    @classmethod
    def from_partial(
        cls,
        owner: str,
        repo: str,
        clone_url: Optional[str] = None,
        default_branch: Optional[str] = None,
        mode: Optional[str] = None,
    ) -> "RepoContext":
        repo_id = cls.derive_id(owner, repo)
        url = clone_url or cls.build_clone_url(owner, repo)
        ctx = cls(
            id=repo_id,
            owner=owner,
            repo=repo,
            clone_url=url,
            default_branch=default_branch or "main",
            mode=RepoMode(mode) if mode else RepoMode.observe,
        )
        return ctx

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["mode"] = self.mode.value
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RepoContext":
        data = dict(data)
        data["mode"] = RepoMode(data.get("mode", "observe"))
        return cls(**data)


def _ensure_state_dir() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)


def load_registry() -> Dict[str, Any]:
    _ensure_state_dir()
    if not REGISTRY_PATH.exists():
        return {"repos": []}
    text = REGISTRY_PATH.read_text(encoding="utf-8")
    try:
        return json.loads(text) if text.strip() else {"repos": []}
    except json.JSONDecodeError:
        return {"repos": []}


def save_registry(reg: Dict[str, Any]) -> None:
    _ensure_state_dir()
    REGISTRY_PATH.write_text(json.dumps(reg, indent=2), encoding="utf-8")


def list_repos() -> List[RepoContext]:
    reg = load_registry()
    return [RepoContext.from_dict(r) for r in reg.get("repos", [])]


def get_repo(repo_id: str) -> Optional[RepoContext]:
    for r in list_repos():
        if r.id == repo_id:
            return r
    return None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def upsert_repo(ctx: RepoContext) -> RepoContext:
    reg = load_registry()
    repos = reg.get("repos", [])
    existing_idx = next((i for i, r in enumerate(repos) if r.get("id") == ctx.id), None)
    if existing_idx is None:
        data = ctx.to_dict()
        data["created_at"] = data.get("created_at") or _now_iso()
        data["updated_at"] = _now_iso()
        repos.append(data)
    else:
        merged = {**repos[existing_idx], **ctx.to_dict()}
        merged["updated_at"] = _now_iso()
        repos[existing_idx] = merged
    reg["repos"] = repos
    save_registry(reg)
    return get_repo(ctx.id)  # type: ignore[return-value]


def patch_repo(repo_id: str, **fields: Any) -> RepoContext:
    reg = load_registry()
    repos = reg.get("repos", [])
    idx = next((i for i, r in enumerate(repos) if r.get("id") == repo_id), None)
    if idx is None:
        raise KeyError(f"repo not found: {repo_id}")

    updated = dict(repos[idx])
    # Only allow specific fields
    allowed = {"mode", "target_subdir", "webhook_secret"}
    for key, value in fields.items():
        if key in allowed:
            if key == "mode" and isinstance(value, str):
                value = RepoMode(value)
            updated[key] = value
    updated["updated_at"] = _now_iso()

    repos[idx] = updated
    reg["repos"] = repos
    save_registry(reg)
    return RepoContext.from_dict(updated)
