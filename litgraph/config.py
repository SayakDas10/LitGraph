from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
PAPERS_DIR = BASE_DIR / "papers"
NOTES_DIR = BASE_DIR / "notes"
DATABASE_FILE = BASE_DIR / ".litgraph.db"
LEGACY_CACHE_FILE = BASE_DIR / ".litgraph.json"
PAPERS_DIR.mkdir(exist_ok=True)
NOTES_DIR.mkdir(exist_ok=True)

ALLOWED_ATTACHMENT_EXTENSIONS = {"ppt", "pptx", "docx", "txt", "pdf", "md"}
MAX_ATTACHMENT_BYTES = int(os.getenv("LITGRAPH_MAX_ATTACHMENT_MB", "50")) * 1024 * 1024
ONLINE_METADATA = os.getenv("LITGRAPH_ONLINE_METADATA", "0").lower() in {"1", "true", "yes"}


def resolved_child(root: Path, relative: str) -> Path:
    """Return a canonical path below root, rejecting absolute paths and traversal."""
    candidate = Path(relative)
    if candidate.is_absolute():
        raise ValueError("Absolute destination paths are not allowed")
    resolved_root = root.resolve()
    resolved = (resolved_root / candidate).resolve()
    if not resolved.is_relative_to(resolved_root):
        raise ValueError("Path escapes the LitGraph data directory")
    return resolved


def paths_overlap(first: Path, second: Path) -> bool:
    """Return True when either canonical path contains the other."""
    a = first.resolve()
    b = second.resolve()
    return a == b or a.is_relative_to(b) or b.is_relative_to(a)

