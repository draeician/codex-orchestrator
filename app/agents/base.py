from ..config import load_settings
from ..registry import RepoContext
from ..adapters.repo_git import RepoHelper
from ..adapters.vcs_github import VCS

class AgentBase:
    def __init__(self, repo_ctx: RepoContext):
        self.settings = load_settings()
        self.repo_ctx = repo_ctx
        self.repo = RepoHelper(repo_ctx, self.settings.workdir_root)
        self.vcs = VCS(repo_ctx, self.settings.gh_token)

