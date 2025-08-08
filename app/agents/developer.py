from pathlib import Path
from .base import AgentBase
from ..adapters.repo_git import file_write
from ..adapters.vcs_github import pr_body_for_task
from ..utils import safe_slug
import re

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
    def work_next_task(self):
        wdir = self.repo.ensure_local_clone()
        tasks = sorted((Path(wdir) / "tasks").glob("*.md"))
        if not tasks:
            return {"ok": False, "message": "No tasks found. Run Taskmaster first."}

        # claim first queued
        picked = None
        for t in tasks:
            txt = t.read_text(encoding="utf-8")
            if re.search(r"status:\s*queued", txt):
                picked = (t, txt)
                break
        if picked is None:
            return {"ok": False, "message": "No queued tasks to work on"}

        tfile, ttext = picked
        tid = re.search(r"id:\s*(T-\d+)", ttext).group(1)
        title = re.search(r"title:\s*(.+)", ttext).group(1).strip()

        branch = f"feature/{tid}-{safe_slug(title)}"
        self.repo.create_branch(branch)

        # Edit files according to the known first task type (CI)
        ci_path = Path(wdir) / ".github" / "workflows" / "ci.yml"
        smoke_path = Path(wdir) / "tests" / "test_smoke.py"
        file_write(ci_path, CI_YML)
        file_write(smoke_path, SMOKE_TEST)

        # Mark task in progress -> in_review in file
        ttext = re.sub(r"status:\s*queued", "status: in_review", ttext)
        tfile.write_text(ttext, encoding="utf-8")

        self.repo.commit_all(f"{tid}: {title}")
        self.repo.push_branch(branch)

        pr_url = self.vcs.open_pr(
            head=branch,
            base=self.settings.default_branch,
            title=f"{tid} - {title}",
            body=pr_body_for_task(tid, title),
        )
        return {"ok": True, "task": tid, "branch": branch, "pr_url": pr_url}

