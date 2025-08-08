from .base import AgentBase
from ..adapters.ci_checks import summarize_repo_checks

class Reviewer(AgentBase):
    def review_pull_request(self, pr_event_payload: dict):
        repo = pr_event_payload.get("repository", {})
        pr = pr_event_payload.get("pull_request", {})
        number = pr.get("number")
        head = pr.get("head", {}).get("ref")

        summary = summarize_repo_checks()
        body = f"Automated review summary for `{head}`:\n\n{summary}\n\nIf checks are green and acceptance criteria are met, mark task status to `ready_for_integration`."

        self.vcs.comment_on_pr(number, body)
        return {"ok": True, "pr": number}

