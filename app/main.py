from fastapi import FastAPI, Request
from .router import handle_pr_event, run_taskmaster, run_developer

app = FastAPI(title="Poor Man Codex Orchestrator", version="0.1.0")

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/webhook")
async def webhook(request: Request):
    payload = await request.json()
    event = request.headers.get("X-GitHub-Event", "")
    if event == "pull_request":
        handle_pr_event(payload)
    return {"received": True, "event": event}

@app.post("/run/taskmaster")
def run_taskmaster_endpoint():
    return run_taskmaster()

@app.post("/run/developer")
def run_developer_endpoint():
    return run_developer()

