from ..config import load_settings
from ..adapters.repo_git import RepoHelper
from ..adapters.vcs_github import VCS

class AgentBase:
    def __init__(self):
        self.settings = load_settings()
        self.repo = RepoHelper(self.settings)
        self.vcs = VCS(self.settings)

