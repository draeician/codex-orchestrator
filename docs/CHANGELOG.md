# Changelog

- M1: repo registry, per-repo modes (observe/pr/disabled), per-repo webhook routing, task scan & work-next endpoints.
- feat: add ETag-based poller + rate-limit awareness; endpoints /poll/once and /repos/{id}/poll
 - feat(integrator): auto-open mark-done PRs; idempotent
 - fix(poller): first-run closed-PR detection avoids missing merges
