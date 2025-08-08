def summarize_repo_checks() -> str:
    return (
        "- Lints (ruff): required; CI fails on violations\n"
        "- Types (mypy): required; CI fails on errors\n"
        "- Tests: pytest executed in CI\n"
        "- Coverage: not enforced in MVP\n"
        "- Acceptance: developer must confirm in PR body\n"
    )

