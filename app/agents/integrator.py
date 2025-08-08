import re
from pathlib import Path
from git import GitCommandError
import httpx
from .base import AgentBase

class Integrator(AgentBase):
    def __init__(self, repo_ctx):
        super().__init__(repo_ctx)

    def on_merge(self, pr_event_payload: dict):
        # Always ensure an integration mark-done PR exists for T-XXXX
        pr = pr_event_payload.get("pull_request", {})
        title = pr.get("title", "")
        m = re.search(r"(T-\d+)", title or "")
        if not m:
            return {"ok": True, "message": "No task id found in title"}

        tid = m.group(1)
        wdir = self.repo.ensure_local_clone()
        branch = f"integration/{tid}-mark-done"

        # Ensure branch exists locally (create or track remote)
        try:
            local_branches = set(self.repo.list_local_branches())
            remote_branches = set(self.repo.list_remote_branches())
            if branch in local_branches:
                self.repo.create_branch(branch)
            elif branch in remote_branches:
                repo = self.repo._repo()
                try:
                    repo.git.fetch("origin", branch)
                except Exception:
                    pass
                repo.git.checkout("-B", branch, f"origin/{branch}")
            else:
                self.repo.create_branch(branch)
        except Exception:
            # Fallback to simple create/checkout
            self.repo.create_branch(branch)

        # Modify matching task file(s): set status -> done (idempotent)
        updated = 0
        for t in (Path(wdir) / "tasks").glob("*.md"):
            txt = t.read_text(encoding="utf-8")
            if f"id: {tid}" not in txt:
                continue
            new_txt, n = re.subn(r"status:\s*[^\n\r]+", "status: done", txt, count=1)
            if n > 0 and new_txt != txt:
                t.write_text(new_txt, encoding="utf-8")
                updated += 1

        # Commit with conventional message (only if there are changes)
        commit_msg = f"chore(tasks): {tid} mark done"
        self.repo.commit_all(commit_msg)

        # Push branch with a single fetch/retry on non-fast-forward
        try:
            self.repo.push_branch(branch)
        except GitCommandError as e:
            msg = str(e).lower()
            if "non-fast-forward" in msg or "fetch first" in msg or "rejected" in msg:
                repo = self.repo._repo()
                try:
                    repo.git.fetch("origin", branch)
                    # Rebase local onto remote if needed
                    try:
                        repo.git.rebase(f"origin/{branch}")
                    except Exception:
                        pass
                except Exception:
                    pass
                # Retry push once
                self.repo.push_branch(branch)
            else:
                raise

        # Open PR if not already open; otherwise reuse existing
        existing = self.vcs.get_open_pr_by_head(head=branch, base=self.settings.default_branch)
        if not existing:
            body = f"Mark task {tid} as done."
            try:
                self.vcs.open_pr(
                    head=branch,
                    base=self.settings.default_branch,
                    title=f"{tid} - mark task done",
                    body=body,
                )
            except httpx.HTTPStatusError as e:
                # If there is nothing to compare (422), treat as no-op and try to discover existing/closed state
                if e.response is None or e.response.status_code != 422:
                    raise
            existing = self.vcs.get_open_pr_by_head(head=branch, base=self.settings.default_branch)

        pr_number = existing.get("number") if isinstance(existing, dict) else None
        owner_repo = f"{self.repo_ctx.owner}/{self.repo_ctx.repo}"
        if pr_number is not None:
            print(f"integrator: opened mark-done PR #{pr_number} for {tid} in {owner_repo}")
        else:
            print(f"integrator: opened mark-done PR for {tid} in {owner_repo}")

        return {"ok": True, "tid": tid, "updated": updated, "pr_number": pr_number}

