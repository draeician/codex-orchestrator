import hmac
import hashlib
from typing import Optional

from fastapi import HTTPException


def verify_signature(request, secret: str, body: bytes) -> None:
    """Verify GitHub webhook signature if a secret is configured.

    - If secret is empty, no verification is performed.
    - Supports 'X-Hub-Signature-256' header with 'sha256=' prefix.
    - Raises HTTPException(401) on invalid signature.
    """
    if not secret:
        return

    sig_header: Optional[str] = request.headers.get("X-Hub-Signature-256")
    if not sig_header or not sig_header.startswith("sha256="):
        raise HTTPException(status_code=401, detail="missing or invalid signature header")

    provided = sig_header.split("=", 1)[1].strip()
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()

    if not hmac.compare_digest(provided, digest):
        raise HTTPException(status_code=401, detail="signature mismatch")
