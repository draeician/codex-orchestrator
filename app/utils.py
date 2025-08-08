from pathlib import Path

def safe_slug(text: str) -> str:
    s = "".join(c if c.isalnum() or c in "-_ " else "-" for c in text).strip()
    return "-".join(s.lower().split())

def ensure_dir(path: str) -> str:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return str(p)

