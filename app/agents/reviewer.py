import re
from .base import AgentBase
from ..adapters.ci_checks import summarize_repo_checks


class Reviewer(AgentBase):
    def __init__(self, repo_ctx):
        super().__init__(repo_ctx)

    def review_pull_request(self, pr_event_payload: dict):
        pr = pr_event_payload.get("pull_request", {})
        number = pr.get("number")
        head_ref = pr.get("head", {}).get("ref", "")
        title = pr.get("title", "")
        body_text = pr.get("body", "") or ""

        # Try to extract linked task id from PR title
        tid_match = re.search(r"(T-\d+)", title or "")
        task_id = tid_match.group(1) if tid_match else None

        checks_summary = summarize_repo_checks()

        lines = []
        lines.append(f"Automated review summary for `{head_ref}`")
        lines.append("")
        lines.append(f"- Head ref: `{head_ref}`")
        lines.append(f"- Linked task: `{task_id}`" if task_id else "- Linked task: not detected in title")
        lines.append("")
        lines.append("### CI checklist")
        lines.append(checks_summary.rstrip())
        lines.append("")
        lines.append("### Documentation")
        if "docs/CHANGELOG.md" in body_text or "CHANGELOG" in body_text:
            lines.append("- OK: PR body references CHANGELOG updates")
        else:
            lines.append("- Warning: PR body does not reference docs/CHANGELOG.md; ensure it is updated and linked")
        lines.append("")
        lines.append("### Acceptance reminder")
        if task_id:
            lines.append(f"- Validate acceptance criteria in `{task_id}` task file and PR body checklist")
        else:
            lines.append("- Validate acceptance criteria in the linked task and PR body checklist")
        lines.append("- Keep changes minimal and focused; avoid protected paths")

        body = "\n".join(lines)

        if number is not None:
            self.vcs.comment_on_pr(int(number), body)
        return {"ok": True, "pr": number, "task": task_id, "head": head_ref}
