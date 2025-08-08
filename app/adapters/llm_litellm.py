import os
from typing import Optional

try:
    from litellm import completion  # type: ignore
except Exception:
    completion = None  # LLM disabled if import fails


_ROLE_ENV = {
    "planner": ("LLM_PLANNER_MODEL", "qwen3:32b"),
    "taskmaster": ("LLM_TASKMASTER_MODEL", "qwen3:32b"),
    "developer": ("LLM_DEVELOPER_MODEL", "qwen3-coder:latest"),
    "reviewer": ("LLM_REVIEWER_MODEL", "qwen3:32b"),
    "integrator": ("LLM_INTEGRATOR_MODEL", "none"),
}


def _model_for_role(role: str) -> Optional[str]:
    env_key, default_val = _ROLE_ENV.get(role, ("LLM_DEVELOPER_MODEL", "qwen3-coder:latest"))
    val = os.environ.get(env_key, default_val).strip()
    if val.lower() == "none" or val == "":
        return None
    return val


def _temperature_for_role(role: str) -> float:
    # Defaults: Dev/Reviewer 0.15; Planner/Taskmaster 0.35; others 0.15
    if role in ("planner", "taskmaster"):
        return 0.35
    return 0.15


def plan_changes(prompt: str, role: str = "developer") -> str:
    """Return a 3–5 line plan for the change.

    If LiteLLM or OLLAMA_BASE_URL/model is not configured, return a stub.
    """
    base = os.environ.get("OLLAMA_BASE_URL", "http://aether:11434").strip()
    model_name = _model_for_role(role)
    if completion is None or not base or not model_name:
        return "(stub) Plan: make minimal change per acceptance criteria."

    try:
        resp = completion(
            model=f"ollama/{model_name}",
            messages=[
                {
                    "role": "system",
                    "content": "You produce concise 3–5 line implementation plans with clear steps.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=_temperature_for_role(role),
            max_tokens=300,
            api_base=base,
        )
        return resp["choices"][0]["message"]["content"].strip()
    except Exception:
        return "(stub) Plan: make minimal change per acceptance criteria."

