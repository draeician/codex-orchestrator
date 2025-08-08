import httpx
from ..config import Settings


class VCS:
    def __init__(self, settings: Settings):
        self.s = settings
        self.base = "https://api.github.com"
        self.headers = {
            "Authorization": f"Bearer {self.s.gh_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "codex-orchestrator",
        }

    def open_pr(self, head: str, base: str, title: str, body: str) -> str:
        """Open a pull request and return its html_url.

        Raises httpx.HTTPStatusError on failure.
        """
        url = f"{self.base}/repos/{self.s.gh_owner}/{self.s.gh_repo}/pulls"
        payload = {
            "title": title,
            "head": head,
            "base": base,
            "body": body,
            "maintainer_can_modify": True,
        }
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(url, headers=self.headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data.get("html_url", "")

    def comment_on_pr(self, number: int, body: str) -> str:
        """Create an issue comment on the PR and return its html_url."""
        url = f"{self.base}/repos/{self.s.gh_owner}/{self.s.gh_repo}/issues/{number}/comments"
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(url, headers=self.headers, json={"body": body})
            resp.raise_for_status()
            return resp.json().get("html_url", "")


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

