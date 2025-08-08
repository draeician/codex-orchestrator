import re
import logging
from pathlib import Path
from git import GitCommandError
import httpx
from .base import AgentBase

logger = logging.getLogger(__name__)

class Integrator(AgentBase):
    def __init__(self, repo_ctx):
        super().__init__(repo_ctx)

    def _ensure_task_file(self, repo_ctx, task_id: str, repo) -> str:
        """
        Ensure tasks/<task_id>-*.md exists in the working tree.
        Return the relative path to the file.
        Strategy:
          1) Look for a file under 'tasks/' that starts with f"{task_id}-" and endswith ".md".
             If found, return it.
          2) If not found, `repo.git.fetch("origin")`, then list tasks on origin/<default_base>:
               repo.git.ls_tree('-r','--name-only', f"origin/{self.settings.default_branch}", 'tasks')
             Pick the first path that startswith f"tasks/{task_id}-" and endswith ".md".
             If found, `repo.git.checkout(f"origin/{self.settings.default_branch}", "--", found_path)`, then return it.
          3) If still not found, raise a clear error: f"Task file for {task_id} not found on origin/main".
        """
        workdir = Path(self.repo.ensure_local_clone())
        tasks_dir = workdir / "tasks"
        if tasks_dir.exists():
            for p in sorted(tasks_dir.glob("*.md")):
                name = p.name
                if name.startswith(f"{task_id}-") and name.endswith(".md"):
                    return f"tasks/{name}"

        # Not found locally: fetch and inspect origin/<base>
        try:
            repo.git.fetch("origin")
        except Exception:
            pass

        try:
            output = repo.git.ls_tree("-r", "--name-only", f"origin/{self.settings.default_branch}", "tasks")
        except Exception:
            output = ""
        for line in (output or "").splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith(f"tasks/{task_id}-") and line.endswith(".md"):
                # Checkout that file from origin/<base> into working tree
                try:
                    repo.git.checkout(f"origin/{self.settings.default_branch}", "--", line)
                except Exception:
                    # If checkout fails, continue searching
                    pass
                # Verify file now exists
                if (workdir / line).exists():
                    return line

        raise FileNotFoundError(f"Task file for {task_id} not found on origin/main")

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

        # Ensure the specific task file exists, then set status -> done (idempotent)
        repo = self.repo._repo()
        rel_path = self._ensure_task_file(self.repo_ctx, tid, repo)
        tpath = Path(wdir) / rel_path
        updated = 0
        if tpath.exists():
            txt = tpath.read_text(encoding="utf-8")
            # Flip queued|in_review to done; noop if already done
            new_txt, n = re.subn(r"status:\s*(queued|in_review)\b", "status: done", txt, count=1)
            if n > 0 and new_txt != txt:
                tpath.write_text(new_txt, encoding="utf-8")
                updated = 1

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
            body = "Flip task to done after feature PR merge."
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
        logger.info(
            "integrator: mark-done PR #%s for %s in %s/%s",
            pr_number,
            tid,
            self.repo_ctx.owner,
            self.repo_ctx.repo,
        )

        return {"ok": True, "tid": tid, "updated": updated, "pr_number": pr_number}

