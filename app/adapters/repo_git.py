import os
from pathlib import Path
from git import Repo, GitCommandError
from typing import Optional
from ..config import Settings
from ..utils import ensure_dir

def file_write(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")

class RepoHelper:
    def __init__(self, settings: Settings):
        self.s = settings
        ensure_dir(self.s.workdir_root)
        self.local_path = os.path.join(self.s.workdir_root, f"{self.s.gh_owner}_{self.s.gh_repo}")

    def ensure_local_clone(self) -> str:
        if not os.path.exists(self.local_path):
            Repo.clone_from(self.s.project_clone_url, self.local_path)
        return self.local_path

    def _repo(self) -> Repo:
        self.ensure_local_clone()
        return Repo(self.local_path)

    def create_branch(self, name: str):
        repo = self._repo()
        try:
            repo.git.checkout("-b", name)
        except GitCommandError:
            repo.git.checkout(name)

    def commit_all(self, message: str):
        repo = self._repo()
        repo.git.add(all=True)
        if repo.is_dirty():
            repo.index.commit(message)

    def commit_and_push(self, message: str, branch: Optional[str] = None):
        repo = self._repo()
        repo.git.add(all=True)
        if repo.is_dirty():
            repo.index.commit(message)
        if branch:
            repo.git.push("--set-upstream", "origin", branch)
        else:
            repo.git.push()

    def push_branch(self, branch: str):
        repo = self._repo()
        repo.git.push("--set-upstream", "origin", branch)

