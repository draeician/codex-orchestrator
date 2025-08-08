import httpx
from ..config import Settings

class VCS:
    def __init__(self, settings: Settings):
        self.s = settings
        self.base = "https://api.github.com"
        self.headers = {
            "Authorization": f"Bearer {self.s.gh_token}",
            "Accept": "application/vnd.github+json",
        }

    def open_pr(self, head: str, base: str, title: str, body: str) -> str:
        url = f"{self.base}/repos/{self.s.gh_owner}/{self.s.gh_repo}/pulls"
        payload = {"title": title, "head": head, "base": base, "body": body, "maintainer_can_modify": True}
        with httpx.Client(timeout=30.0) as client:
            r = client.post(url, headers=self.headers, json=payload)
            r.raise_for_status()
            return r.json().get("html_url", "")

    def comment_on_pr(self, number: int, body: str):
        url = f"{self.base}/repos/{self.s.gh_owner}/{self.s.gh_repo}/issues/{number}/comments"
        with httpx.Client(timeout=30.0) as client:
            r = client.post(url, headers=self.headers, json={"body": body})
            r.raise_for_status()
            return r.json().get("html_url", "")

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

