from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import httpx

from .registry import RepoContext
from .adapters.repo_git import RepoHelper
from .adapters.vcs_github import VCS


# ---- Task file parsing ----

def _parse_front_matter(text: str) -> Tuple[Dict[str, Any], str]:
    """Parse a simple YAML-like front matter delimited by '---' lines.

    Supports flat key: value pairs, integer values, and simple list values for
    keys like depends_on, acceptance using either inline list syntax (e.g., [a, b])
    or block list syntax:
        depends_on:
          - T-0001
          - T-0002

    Returns (front_matter_dict, body_text).
    """
    fm: Dict[str, Any] = {}
    body = text

    if not text.startswith("---"):
        return fm, body

    # Find the closing delimiter for front matter
    # Accept either "\n---\n" or "\n---\r\n" patterns
    # Start search from after the first three dashes
    closing_idx = None
    for m in re.finditer(r"\n---\s*\n", text):
        # First match after position 3 (post opening '---')
        if m.start() > 3:
            closing_idx = m.start()
            break
    if closing_idx is None:
        return fm, body

    header = text[3:closing_idx].strip("\n\r ")
    body = text[closing_idx + len("\n---\n"):]

    current_list_key: Optional[str] = None
    for raw_line in header.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            continue
        # Continuation of block list
        if current_list_key is not None and re.match(r"^\s*-\s+", line):
            item = re.sub(r"^\s*-\s+", "", line).strip()
            if item:
                fm[current_list_key].append(item)
            continue
        # New key
        m = re.match(r"^(?P<key>[A-Za-z0-9_]+):\s*(?P<value>.*)$", line)
        if not m:
            # Not a key-value line; end any pending list
            current_list_key = None
            continue
        key = m.group("key")
        value = m.group("value").strip()

        # Start of block list with empty value
        if value == "":
            fm[key] = []
            current_list_key = key
            continue
        current_list_key = None

        # Inline list like [a, b]
        if value.startswith("[") and value.endswith("]"):
            inner = value[1:-1].strip()
            if not inner:
                fm[key] = []
            else:
                parts = [p.strip().strip("'\"") for p in inner.split(",")]
                fm[key] = [p for p in parts if p]
            continue

        # Try to coerce integers for numeric fields like order
        if re.fullmatch(r"-?\d+", value):
            try:
                fm[key] = int(value)
                continue
            except ValueError:
                pass

        # Fallback to plain string
        fm[key] = value

    return fm, body.lstrip("\n")


def parse_task_file(path: str | Path) -> Dict[str, Any]:
    """Parse a task markdown file with front matter.

    Returns a dict containing all parsed front-matter fields plus:
      - id: str (if present)
      - title: str (if present)
      - status: str (default "queued")
      - priority: str (e.g., P0..P3; default P2)
      - depends_on: list[str]
      - order: Optional[int]
      - body: str (markdown body)
      - path: str (file path)
    """
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    fm, body = _parse_front_matter(text)

    task: Dict[str, Any] = dict(fm)
    task.setdefault("status", "queued")
    task.setdefault("priority", "P2")
    task.setdefault("depends_on", [])
    task.setdefault("order", None)
    # Optional future extension: tasks may declare affected paths within a monorepo
    # via a `paths: ["services/api", ...]` field to further fence execution.
    # TODO: enforce path fences when present.
    task["body"] = body
    task["path"] = str(p)
    return task


def load_tasks(repo_root: str | Path) -> List[Dict[str, Any]]:
    """Load all tasks from `<repo_root>/tasks/*.md`.

    Note: Even with monorepo targeting, tasks are discovered only at the
    repository root `tasks/` folder for now.
    """
    root = Path(repo_root)
    tasks_dir = root / "tasks"
    tasks: List[Dict[str, Any]] = []
    if not tasks_dir.exists():
        return tasks
    for f in sorted(tasks_dir.glob("*.md")):
        try:
            tasks.append(parse_task_file(f))
        except Exception:
            # Skip malformed files but keep scanning others
            continue
    return tasks


def build_task_graph(tasks: List[Dict[str, Any]]) -> Tuple[Dict[str, List[str]], Dict[str, int], Dict[str, Dict[str, Any]]]:
    """Build a dependency graph from tasks using `depends_on`.

    Returns (graph, indegree, lookup) where:
      - graph: task_id -> list of dependent task_ids
      - indegree: task_id -> number of incoming edges
      - lookup: task_id -> task dict
    """
    lookup: Dict[str, Dict[str, Any]] = {}
    for t in tasks:
        tid = str(t.get("id", "")).strip()
        if tid:
            lookup[tid] = t

    graph: Dict[str, List[str]] = {tid: [] for tid in lookup.keys()}
    indegree: Dict[str, int] = {tid: 0 for tid in lookup.keys()}

    for tid, t in lookup.items():
        deps = t.get("depends_on") or []
        if not isinstance(deps, list):
            continue
        for dep in deps:
            dep_id = str(dep).strip()
            if not dep_id or dep_id not in lookup:
                # Ignore edges to unknown tasks in graph construction
                # (eligibility will still treat unknown deps as unsatisfied)
                continue
            graph.setdefault(dep_id, []).append(tid)
            indegree[tid] = indegree.get(tid, 0) + 1

    return graph, indegree, lookup


def list_eligible(
    tasks: List[Dict[str, Any]],
    open_pr_titles: Set[str],
    *,
    repo_helper: Optional[RepoHelper] = None,
) -> List[Dict[str, Any]]:
    """Return eligible tasks:
    - status == queued
    - dependencies satisfied and valid (unknown deps block the task)
    - id not mentioned in any open PR title
    - no existing feature/{tid}-* branch locally or remotely
    """
    _, _, lookup = build_task_graph(tasks)

    # Pre-compute title strings for fast membership checks
    titles = list(open_pr_titles)

    def deps_satisfied(task: Dict[str, Any]) -> bool:
        deps = task.get("depends_on") or []
        if not isinstance(deps, list):
            return True
        for dep in deps:
            dep_id = str(dep).strip()
            if not dep_id:
                continue
            dep_task = lookup.get(dep_id)
            if dep_task is None:
                # Unknown dependency: treat as not satisfied
                return False
            dep_status = str(dep_task.get("status", "")).lower()
            if dep_status not in {"done", "merged", "completed", "closed"}:
                return False
        return True

    elig: List[Dict[str, Any]] = []
    # Pre-compute branch names to exclude duplicates
    existing_branches: Set[str] = set()
    if repo_helper is not None:
        try:
            # Combine local and remote branches
            existing_branches.update(repo_helper.list_all_branches())
        except Exception:
            pass

    for t in tasks:
        status = str(t.get("status", "")).lower()
        if status != "queued":
            continue
        tid = str(t.get("id", "")).strip()
        if not tid:
            continue
        # Check PR titles for the task id
        in_any_title = any(tid in title for title in titles)
        if in_any_title:
            continue
        # Check existing branches for feature/{tid}-*
        if existing_branches:
            prefix = f"feature/{tid}-"
            if any(b == prefix[:-1] or b.startswith(prefix) for b in existing_branches):
                continue
        if not deps_satisfied(t):
            continue
        # Ensure optional numeric order field normalized (or None)
        if "order" in t and t["order"] is not None:
            try:
                t["order"] = int(t["order"])  # type: ignore[assignment]
            except Exception:
                t["order"] = None
        else:
            t["order"] = None
        elig.append(t)
    return elig


def order_tasks(eligible: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Order eligible tasks by priority (P0..P3), then numeric order (None last), then id."""
    prio_rank = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}

    def key(t: Dict[str, Any]):
        pr = str(t.get("priority", "P3")).upper()
        pr_rank = prio_rank.get(pr, 99)
        ord_val = t.get("order")
        ord_rank = (ord_val if isinstance(ord_val, int) else None)
        # None should sort after any integer -> use tuple key
        tid = str(t.get("id", "ZZZZ"))
        return (pr_rank, ord_rank is None, ord_rank or 0, tid)

    return sorted(eligible, key=key)


# ---- GitHub helpers ----

def list_open_prs(vcs: VCS) -> List[Dict[str, Any]]:
    """List open PRs with minimal fields: number, title, head."""
    url = f"{vcs.base}/repos/{vcs.repo_ctx.owner}/{vcs.repo_ctx.repo}/pulls"
    params = {"state": "open", "per_page": 100}
    with httpx.Client(timeout=30.0) as client:
        resp = client.get(url, headers=vcs.headers, params=params)
        resp.raise_for_status()
        prs: List[Dict[str, Any]] = resp.json()
    minimal = []
    for pr in prs:
        minimal.append(
            {
                "number": pr.get("number"),
                "title": pr.get("title", ""),
                "head": (pr.get("head") or {}).get("ref", ""),
            }
        )
    return minimal


def list_open_pr_titles(vcs: VCS) -> Set[str]:
    return {pr.get("title", "") for pr in list_open_prs(vcs)}


# ---- Scan orchestration ----

def _present_signals(repo_root: str | Path) -> Dict[str, bool]:
    root = Path(repo_root)

    def any_exists(paths: List[str]) -> bool:
        return any((root / p).exists() for p in paths)

    has_tasks = (root / "tasks").exists() and any((root / "tasks").glob("*.md"))
    has_prd = any_exists(
        [
            "PRD.md",
            "prd.md",
            "docs/PRD.md",
            "docs/prd.md",
            "docs/product_requirements.md",
            "product/PRD.md",
        ]
    )
    has_ci = (root / ".github/workflows").exists() and (
        any((root / ".github/workflows").glob("*.yml"))
        or any((root / ".github/workflows").glob("*.yaml"))
    )
    has_pr_template = any_exists(
        [
            ".github/pull_request_template.md",
            ".github/PULL_REQUEST_TEMPLATE.md",
            "PULL_REQUEST_TEMPLATE.md",
        ]
    )
    has_codeowners = any_exists([".github/CODEOWNERS", "CODEOWNERS"])

    has_llm_team = False
    # Heuristics: CODEOWNERS contains 'llm' token or special marker file exists
    for path in [".github/CODEOWNERS", "CODEOWNERS", ".github/llm-team.md", "docs/llm-team.md"]:
        fpath = root / path
        if fpath.exists():
            if fpath.name.lower().endswith("codeowners"):
                try:
                    txt = fpath.read_text(encoding="utf-8", errors="ignore").lower()
                    if "llm" in txt or "ai" in txt:
                        has_llm_team = True
                        break
                except Exception:
                    pass
            else:
                has_llm_team = True
                break

    return {
        "has_tasks": has_tasks,
        "has_prd": has_prd,
        "has_ci": has_ci,
        "has_pr_template": has_pr_template,
        "has_codeowners": has_codeowners,
        "has_llm_team": has_llm_team,
    }


def scan_repo(repo_ctx: RepoContext, workdir_root: str, gh_token: str) -> Dict[str, Any]:
    """Scan a repository and compute next eligible task.

    Returns a report dict with keys:
      - present: {has_tasks, has_prd, has_ci, has_pr_template, has_codeowners, has_llm_team}
      - open_prs: list of {number, title, head}
      - next_task: {id, title} or None

    Monorepo note: If `repo_ctx.target_subdir` is set, we still discover tasks from
    the repository root `tasks/` folder. Future extension: tasks may include a
    `paths: [...]` field to fence applicability to certain subdirectories.
    """
    # Ensure local clone available
    repo = RepoHelper(repo_ctx, workdir_root)
    repo_root = Path(repo.ensure_local_clone())

    # Load tasks from repo root
    tasks = load_tasks(repo_root)

    # GitHub VCS for listing PRs
    vcs = VCS(repo_ctx, gh_token)
    open_prs = list_open_prs(vcs)
    open_titles = {pr["title"] for pr in open_prs}

    eligible = list_eligible(tasks, open_titles, repo_helper=repo)
    ordered = order_tasks(eligible)

    next_task: Optional[Dict[str, Any]] = ordered[0] if ordered else None
    next_task_min = {"id": next_task.get("id"), "title": next_task.get("title")} if next_task else None

    report: Dict[str, Any] = {
        "present": _present_signals(repo_root),
        "open_prs": open_prs,
        "next_task": next_task_min,
    }
    return report
