from pydantic import BaseModel
import os

class Settings(BaseModel):
    gh_token: str
    gh_owner: str
    gh_repo: str
    project_clone_url: str
    default_branch: str = "main"
    workdir_root: str = "/tmp/codex-work"

def load_settings() -> Settings:
    return Settings(
        gh_token=os.environ.get("GH_TOKEN", ""),
        gh_owner=os.environ.get("GH_OWNER", ""),
        gh_repo=os.environ.get("GH_REPO", ""),
        project_clone_url=os.environ.get("PROJECT_CLONE_URL", ""),
        default_branch=os.environ.get("DEFAULT_BRANCH", "main"),
        workdir_root=os.environ.get("WORKDIR_ROOT", "/tmp/codex-work"),
    )

