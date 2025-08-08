from .agents.taskmaster import Taskmaster
from .agents.developer import Developer
from .agents.reviewer import Reviewer
from .agents.integrator import Integrator
from .config import load_settings

settings = load_settings()

def handle_pr_event(event_payload: dict):
    action = event_payload.get("action", "")
    if action in {"opened", "synchronize"}:
        Reviewer().review_pull_request(event_payload)
    elif action == "closed" and event_payload.get("pull_request", {}).get("merged"):
        Integrator().on_merge(event_payload)

def run_taskmaster():
    return Taskmaster().generate_or_update_tasks()

def run_developer():
    return Developer().work_next_task()

