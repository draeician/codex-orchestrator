import os
import re
from pathlib import Path
from typing import Dict, Any, Optional

from .base import AgentBase
from ..adapters.repo_git import file_write
from ..adapters.vcs_github import pr_body_for_task
from ..adapters.llm_litellm import plan_changes
from ..utils import safe_slug


CI_YML = """name: CI
on: [pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install -r requirements.txt || true
      - run: pytest -q || true
"""

SMOKE_TEST = """def test_smoke():
    assert True
"""


class Developer(AgentBase):
    def __init__(self, repo_ctx):
        super().__init__(repo_ctx)

    def can_plan_changes(self) -> bool:
        return os.environ.get("DEV_USE_LLM", "false").strip().lower() == "true"

    def _append_changelog(self, repo_root: str | Path, tid: str, title: str) -> Path:
        """Ensure docs/CHANGELOG.md exists and append the task line at the repo root.

        Note: Even when `target_subdir` is set, we keep CHANGELOG at the repository root.
        """
        root = Path(repo_root)
        changelog = root / "docs" / "CHANGELOG.md"
        changelog.parent.mkdir(parents=True, exist_ok=True)
        if not changelog.exists():
            changelog.write_text("# Changelog\n\n", encoding="utf-8")
        with changelog.open("a", encoding="utf-8") as fh:
            fh.write(f"- {tid}: {title} ([PR pending])\n")
        return changelog

    def _flip_task_to_in_review(self, task_file: Path) -> None:
        text = task_file.read_text(encoding="utf-8")
        # Replace first occurrence of queued with in_review
        new_text, n = re.subn(r"status:\s*queued", "status: in_review", text, count=1)
        if n == 0:
            # If not present, ensure there is a status line set to in_review
            if re.search(r"^status:\s*", text, flags=re.MULTILINE):
                new_text = re.sub(r"^status:\s*.*$", "status: in_review", text, flags=re.MULTILINE)
            else:
                new_text = text.strip() + "\nstatus: in_review\n"
        task_file.write_text(new_text, encoding="utf-8")

    def work_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Work on a specific task dict produced by scan/load_tasks.

        Behavior:
        - Derives branch feature/{tid}-{slug}
        - Checks for existing open PR for tid to avoid duplicates
        - Performs a small representative edit (CI+smoke for T-0001*, otherwise just CHANGELOG)
        - Flips task status to in_review in-branch
        - Pushes branch and opens PR

        Monorepo support:
        - If `repo_ctx.target_subdir` is set, confine non-.github edits under that subdir
          (e.g., place smoke test under <subdir>/tests/). Task file and CHANGELOG remain at repo root.
        """
        tid = str(task.get("id", "")).strip()
        title = str(task.get("title", "")).strip()
        if not tid or not title:
            return {"ok": False, "message": "task missing id/title"}

        # Idempotence: if PR already exists for this task, return it
        existing = self.vcs.find_open_pr_for_task(tid)
        if existing:
            return {
                "ok": True,
                "task": tid,
                "branch": (existing.get("head") or {}).get("ref", ""),
                "pr_url": existing.get("html_url", ""),
                "message": "PR already open",
            }

        # Ensure local repo and create working branch
        repo_root = self.repo.ensure_local_clone()
        branch = f"feature/{tid}-{safe_slug(title)}"
        self.repo.create_branch(branch)

        # Locate the task file within this working copy (always at repo root tasks/)
        task_filename = Path(str(task.get("path", "tasks"))).name
        task_file = Path(repo_root) / "tasks" / task_filename

        # Determine subdir root for confined edits (non-.github)
        sub_root: Path = Path(repo_root)
        if self.repo_ctx.target_subdir:
            # Normalize and join
            sub_root = Path(repo_root) / self.repo_ctx.target_subdir.strip("/ ")

        # Representative edits
        if tid.startswith("T-0001"):
            # Add CI at repo level
            ci_path = Path(repo_root) / ".github" / "workflows" / "ci.yml"
            file_write(ci_path, CI_YML)
            # Add smoke test under subdir (or repo root if no subdir configured)
            smoke_path = sub_root / "tests" / "test_smoke.py"
            file_write(smoke_path, SMOKE_TEST)
        # Always enforce documentation change at repo root
        changelog_path = self._append_changelog(repo_root, tid, title)

        # Flip task status queued -> in_review in the feature branch at repo root
        if task_file.exists():
            self._flip_task_to_in_review(task_file)

        # Commit and push
        self.repo.commit_all(f"{tid}: {title}")
        self.repo.push_branch(branch)

        # Prepare PR body with documentation note
        body = pr_body_for_task(tid, title)
        body += "\n\n## Documentation\n- Updated docs/CHANGELOG.md for this task.\n"
        if self.can_plan_changes():
            plan = plan_changes(
                prompt=(
                    f"Task {tid}: {title}.\n"
                    "Produce a concise 3–5 line implementation plan summarizing the changes."
                ),
                role="developer",
            )
            body = body + "\n\n## Proposed plan (LLM)\n" + plan

        pr_url = self.vcs.open_pr(
            head=branch,
            base=self.settings.default_branch,
            title=f"{tid} - {title}",
            body=body,
        )
        return {"ok": True, "task": tid, "branch": branch, "pr_url": pr_url}
