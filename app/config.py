from pydantic import BaseModel
import os


class Settings(BaseModel):
    gh_token: str
    gh_owner: str
    gh_repo: str
    project_clone_url: str
    default_branch: str = "main"
    workdir_root: str = "/tmp/codex-work"

    # LLM / Ollama related (disabled by default if not configured)
    ollama_base_url: str = "http://aether:11434"
    llm_planner_model: str = "qwen3:32b"
    llm_taskmaster_model: str = "qwen3:32b"
    llm_developer_model: str = "qwen3-coder:latest"
    llm_reviewer_model: str = "qwen3:32b"
    llm_integrator_model: str = "none"


def load_settings() -> Settings:
    return Settings(
        gh_token=os.environ.get("GH_TOKEN", ""),
        gh_owner=os.environ.get("GH_OWNER", ""),
        gh_repo=os.environ.get("GH_REPO", ""),
        project_clone_url=os.environ.get("PROJECT_CLONE_URL", ""),
        default_branch=os.environ.get("DEFAULT_BRANCH", "main"),
        workdir_root=os.environ.get("WORKDIR_ROOT", "/tmp/codex-work"),
        ollama_base_url=os.environ.get("OLLAMA_BASE_URL", "http://aether:11434"),
        llm_planner_model=os.environ.get("LLM_PLANNER_MODEL", "qwen3:32b"),
        llm_taskmaster_model=os.environ.get("LLM_TASKMASTER_MODEL", "qwen3:32b"),
        llm_developer_model=os.environ.get("LLM_DEVELOPER_MODEL", "qwen3-coder:latest"),
        llm_reviewer_model=os.environ.get("LLM_REVIEWER_MODEL", "qwen3:32b"),
        llm_integrator_model=os.environ.get("LLM_INTEGRATOR_MODEL", "none"),
    )

