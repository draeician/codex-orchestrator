def summarize_repo_checks() -> str:
    return (
        "- Lints: not enforced in MVP\n"
        "- Tests: pytest executed in CI\n"
        "- Coverage: not enforced in MVP\n"
        "- Acceptance: developer must confirm in PR body\n"
    )

