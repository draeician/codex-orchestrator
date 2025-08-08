from pydantic import BaseModel
from typing import Optional, Dict, Any

class PullRequest(BaseModel):
    number: int
    head_ref: str
    base_ref: str
    title: str
    html_url: str

class PullRequestEvent(BaseModel):
    action: str
    repository: Dict[str, Any]
    pull_request: Dict[str, Any]

