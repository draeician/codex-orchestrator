from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Optional


def lock_path(workdir_root: str, repo_id: str) -> Path:
    """Return the full path to the lock file under `<workdir_root>/state/locks/{id}.lock`."""
    return Path(workdir_root) / "state" / "locks" / f"{repo_id}.lock"


def _ensure_lock_dir(lp: Path) -> None:
    lp.parent.mkdir(parents=True, exist_ok=True)


def acquire(repo_id: str, workdir_root: str, timeout: float = 0) -> bool:
    """Acquire an exclusive, best-effort file lock for a repo.

    - Returns True on success, False if already locked or on failure.
    - If `timeout` > 0, will retry until timeout expires.
    - The lock file contains the current process ID to support safe release.
    """
    lp = lock_path(workdir_root, repo_id)
    _ensure_lock_dir(lp)

    deadline: Optional[float] = time.time() + timeout if timeout and timeout > 0 else None
    while True:
        try:
            # O_CREAT|O_EXCL ensures we fail if the file already exists
            fd = os.open(str(lp), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            try:
                os.write(fd, str(os.getpid()).encode("utf-8"))
            finally:
                os.close(fd)
            return True
        except FileExistsError:
            # Already locked
            if deadline is None or time.time() >= deadline:
                return False
            time.sleep(0.1)
        except Exception:
            # Any other error -> treat as not acquired
            return False


def release(repo_id: str, workdir_root: str) -> None:
    """Release the lock if owned by this process (PID matches).

    If the lock does not exist or is owned by another PID, do nothing.
    """
    lp = lock_path(workdir_root, repo_id)
    try:
        if not lp.exists():
            return
        owner_pid: Optional[int] = None
        try:
            content = lp.read_text(encoding="utf-8").strip()
            if content:
                owner_pid = int(content)
        except Exception:
            owner_pid = None
        # Only remove if owned by this process
        if owner_pid is None or owner_pid == os.getpid():
            lp.unlink(missing_ok=True)
    except Exception:
        # Best-effort release; ignore errors
        return
