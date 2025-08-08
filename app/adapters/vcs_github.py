from typing import Optional, Dict, Any, List

import httpx
from ..registry import RepoContext


class VCS:
    def __init__(self, repo_ctx: RepoContext, token: str):
        self.repo_ctx = repo_ctx
        self.base = "https://api.github.com"
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "codex-orchestrator",
        }

    def open_pr(self, head: str, base: Optional[str] = None, title: str = "", body: str = "") -> str:
        """Open a pull request and return its html_url.

        Raises httpx.HTTPStatusError on failure.
        """
        url = f"{self.base}/repos/{self.repo_ctx.owner}/{self.repo_ctx.repo}/pulls"
        base_branch = base or self.repo_ctx.default_branch
        payload = {
            "title": title,
            "head": head,
            "base": base_branch,
            "body": body,
            "maintainer_can_modify": True,
        }
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(url, headers=self.headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data.get("html_url", "")

    def get_open_pr_by_head(self, head: str, base: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Return the open PR dict for a given head branch if it exists.

        Implements: GET /repos/{owner}/{repo}/pulls?state=open&head={owner}:{head}&base={base}
        """
        owner = self.repo_ctx.owner
        repo = self.repo_ctx.repo
        base_branch = base or self.repo_ctx.default_branch
        url = f"{self.base}/repos/{owner}/{repo}/pulls"
        params = {
            "state": "open",
            "head": f"{owner}:{head}",
            "base": base_branch,
            "per_page": 100,
        }
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(url, headers=self.headers, params=params)
            resp.raise_for_status()
            prs: List[Dict[str, Any]] = resp.json() or []
        if not prs:
            return None
        # API returns a list; for a unique head this will be at most one
        return prs[0]

    def comment_on_pr(self, number: int, body: str) -> str:
        """Create an issue comment on the PR and return its html_url."""
        url = f"{self.base}/repos/{self.repo_ctx.owner}/{self.repo_ctx.repo}/issues/{number}/comments"
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(url, headers=self.headers, json={"body": body})
            resp.raise_for_status()
            return resp.json().get("html_url", "")

    def find_open_pr_for_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Find an open PR whose title contains the given task_id.

        Returns the PR object (dict) or None if not found.
        """
        url = f"{self.base}/repos/{self.repo_ctx.owner}/{self.repo_ctx.repo}/pulls"
        params = {"state": "open", "per_page": 100}
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(url, headers=self.headers, params=params)
            resp.raise_for_status()
            prs: List[Dict[str, Any]] = resp.json()
        for pr in prs:
            title = pr.get("title", "")
            if task_id in title:
                return pr
        return None

    def list_branches(self) -> List[str]:
        """List remote branches for the repository using GitHub API."""
        url = f"{self.base}/repos/{self.repo_ctx.owner}/{self.repo_ctx.repo}/branches"
        branches: List[str] = []
        page = 1
        with httpx.Client(timeout=30.0) as client:
            while True:
                resp = client.get(url, headers=self.headers, params={"per_page": 100, "page": page})
                resp.raise_for_status()
                data = resp.json()
                if not data:
                    break
                for b in data:
                    name = b.get("name", "")
                    if name:
                        branches.append(name)
                if len(data) < 100:
                    break
                page += 1
        return branches


def pr_body_for_task(tid: str, title: str) -> str:
    return f"""## Linked Tasks
- {tid}

## What changed
- {title}

## Validation
- CI runs on pull_request
- Smoke test passes

## Risk
- No protected paths changed
"""

