import re
from pathlib import Path
from .base import AgentBase

TASK_TMPL = """---
id: T-0001
title: Initialize basic CI for Python
type: chore
priority: P2
depends_on: []
status: queued
owner: unassigned
estimate: 2h
acceptance:
  - "On pull_request, CI runs pytest and reports status"
  - "A minimal tests/test_smoke.py exists and passes"
auto_policy: review_required
---

## Description
Set up a basic GitHub Actions workflow for Python with pytest.
Add a minimal smoke test so CI passes.

## Deliverables
- .github/workflows/ci.yml
- tests/test_smoke.py
"""

class Taskmaster(AgentBase):
    def generate_or_update_tasks(self):
        wdir = self.repo.ensure_local_clone()
        tasks_dir = Path(wdir) / "tasks"
        tasks_dir.mkdir(parents=True, exist_ok=True)

        # If there is any queued task already, do nothing
        existing = list(tasks_dir.glob("*.md"))
        for f in existing:
            txt = f.read_text(encoding="utf-8")
            if re.search(r"status:\s*queued", txt):
                return {"ok": True, "message": "Queued task already exists"}

        # Create the first task
        first = tasks_dir / "T-0001-ci-setup.md"
        first.write_text(TASK_TMPL, encoding="utf-8")
        self.repo.commit_and_push("chore: seed T-0001 basic CI task")
        return {"ok": True, "message": "Seeded T-0001"}

