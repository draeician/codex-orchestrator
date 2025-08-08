def summarize_repo_checks() -> str:
    return (
        "- CI: pytest (and ruff/mypy if configured)\n"
        "- Docs: CHANGELOG updated and linked in PR body\n"
        "- Guardrails: No edits to protected paths unless task explicitly allows\n"
    )
