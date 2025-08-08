import os
from pathlib import Path
from typing import Optional

from git import Repo, GitCommandError

from ..config import Settings
from ..utils import ensure_dir


def _make_authed_url(plain_url: str, token: str) -> str:
    """
    Embed a GitHub token in an https remote URL for push access.
    Use the recommended 'x-access-token:<token>@' form.
    """
    if not token or not plain_url.startswith("https://"):
        return plain_url
    # Strip existing creds if any
    root = plain_url.split("://", 1)[1]
    if "@" in root:
        root = root.split("@", 1)[1]
    return f"https://x-access-token:{token}@{root}"


def file_write(path: Path, content: str) -> None:
    """Write text content to a file path, creating parent directories."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class RepoHelper:
    """Lightweight Git helper around a single working clone of the target repo."""

    def __init__(self, settings: Settings):
        self.settings = settings
        ensure_dir(self.settings.workdir_root)
        self.local_path = os.path.join(
            self.settings.workdir_root, f"{self.settings.gh_owner}_{self.settings.gh_repo}"
        )

    def ensure_local_clone(self) -> str:
        """Ensure the repository exists locally and is on the default branch.

        - Clones with an authenticated https URL when GH_TOKEN is provided.
        - Updates the remote URL to the authenticated form for pushing.
        - Checks out the configured default branch (creating a local tracking branch if needed).
        """
        authed_url = _make_authed_url(self.settings.project_clone_url, self.settings.gh_token)

        if not os.path.exists(self.local_path):
            Repo.clone_from(authed_url, self.local_path)

        repo = Repo(self.local_path)
        # Ensure "origin" remote uses authed URL for pushes
        try:
            origin = repo.remotes.origin
            if origin.url != authed_url and authed_url:
                origin.set_url(authed_url)
        except Exception:
            # Remote may not exist in edge cases; create it
            repo.create_remote("origin", authed_url)

        # Fetch and checkout default branch
        try:
            repo.git.fetch("origin", "--prune")
        except GitCommandError:
            pass

        default_branch = self.settings.default_branch
        try:
            repo.git.checkout(default_branch)
        except GitCommandError:
            # Create local branch tracking origin/default_branch
            try:
                repo.git.checkout("-t", f"origin/{default_branch}")
            except GitCommandError:
                # Fallback: create from origin/HEAD
                repo.git.checkout("-B", default_branch)
        return self.local_path

    def _repo(self) -> Repo:
        self.ensure_local_clone()
        return Repo(self.local_path)

    def create_branch(self, name: str) -> None:
        """Create or switch to a branch idempotently."""
        repo = self._repo()
        try:
            repo.git.checkout("-b", name)
        except GitCommandError:
            # Already exists; just switch
            repo.git.checkout(name)

    def commit_all(self, message: str) -> None:
        """Stage all changes and commit if there is anything to commit."""
        repo = self._repo()
        repo.git.add(all=True)
        if repo.is_dirty(untracked_files=True):
            repo.index.commit(message)

    def _push_with_upstream(self, repo: Repo, branch: str) -> None:
        repo.git.push("--set-upstream", "origin", branch)

    def push_branch(self, branch: str) -> None:
        """Push a branch to origin, setting upstream on first push."""
        repo = self._repo()
        # Ensure we're on the branch to push
        try:
            if repo.active_branch.name != branch:
                repo.git.checkout(branch)
        except TypeError:
            # Detached HEAD; checkout desired branch
            repo.git.checkout(branch)

        tracking = None
        try:
            tracking = repo.branches[branch].tracking_branch()
        except Exception:
            tracking = None

        try:
            if tracking is None:
                self._push_with_upstream(repo, branch)
            else:
                repo.git.push("origin", branch)
        except GitCommandError:
            # Retry by setting upstream explicitly
            self._push_with_upstream(repo, branch)

    def commit_and_push(self, message: str, branch: Optional[str] = None) -> None:
        """Commit staged changes (if any) and push the target branch.

        If branch is None, uses the current active branch.
        """
        repo = self._repo()
        self.commit_all(message)
        target_branch = branch or repo.active_branch.name
        self.push_branch(target_branch)

