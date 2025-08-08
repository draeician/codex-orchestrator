import re
from pathlib import Path
from .base import AgentBase

class Integrator(AgentBase):
    def on_merge(self, pr_event_payload: dict):
        # Best effort: flip any "in_review" tasks back to "done" if branch contained T-XXXX
        pr = pr_event_payload.get("pull_request", {})
        title = pr.get("title", "")
        m = re.search(r"(T-\d+)", title or "")
        if not m:
            return {"ok": True, "message": "No task id found in title"}

        tid = m.group(1)
        wdir = self.repo.ensure_local_clone()
        updated = 0
        for t in (Path(wdir) / "tasks").glob("*.md"):
            txt = t.read_text(encoding="utf-8")
            if f"id: {tid}" in txt:
                txt = re.sub(r"status:\s*in_review", "status: done", txt)
                t.write_text(txt, encoding="utf-8")
                updated += 1
        if updated:
            self.repo.commit_and_push(f"{tid}: mark task done")
        return {"ok": True, "tid": tid, "updated": updated}

