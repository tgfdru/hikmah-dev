"""System prompts, kept as Markdown files so the team's sharia reviewer can read
and approve them without reading code. Each file states the stage it serves.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

_DIR = Path(__file__).resolve().parent


@lru_cache(maxsize=None)
def load(name: str) -> str:
    """Return the prompt body (the header comment block is stripped)."""
    text = (_DIR / f"{name}.md").read_text(encoding="utf-8")
    lines = [ln for ln in text.splitlines() if not ln.startswith("<!--")]
    return "\n".join(lines).strip()
