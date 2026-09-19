"""
Knowledge base.

A single plain-markdown file (knowledge_base.md by default - see
config.KNOWLEDGE_BASE_PATH) that *you* edit with whatever personal or
work context you want OGGY to always have: who you are, what you're
working on, preferences, recurring facts you're tired of repeating.

This is deliberately NOT the same thing as memory/memory.py:
  - memory.py is OGGY's own structured, machine-written notes (tool
    history, key/value facts it was told to remember mid-conversation).
  - knowledge_base.md is a human-written document, read-only from
    OGGY's point of view, that you maintain like a text file.

It's re-read from disk on every turn (see load_knowledge_base below).
That's an intentional simplicity/cost tradeoff: it's one small local
file read, not a network call or a DB query, so paying that cost every
turn means edits take effect immediately with zero restart and zero
extra moving parts - in keeping with the rest of V1's "boring on
purpose" storage choices (see memory/memory.py's docstring).
"""

from typing import Optional

from config import config


def load_knowledge_base() -> Optional[str]:
    """
    Read config.KNOWLEDGE_BASE_PATH and return its content, truncated to
    config.KNOWLEDGE_BASE_MAX_CHARS. Returns None if the file doesn't
    exist or is empty/whitespace-only, so callers can skip it cleanly
    instead of injecting an empty section into the system prompt.

    Never raises - a missing, unreadable, or huge file is a normal
    condition here (you may not have filled it in yet), not an error
    that should interrupt a chat turn.
    """
    path = config.KNOWLEDGE_BASE_PATH
    try:
        if not path.is_file():
            return None
        text = path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None

    if not text:
        return None

    limit = config.KNOWLEDGE_BASE_MAX_CHARS
    if limit > 0 and len(text) > limit:
        text = text[:limit].rstrip() + "\n\n[...knowledge_base.md truncated - trim it or raise OGGY_KNOWLEDGE_BASE_MAX_CHARS...]"

    return text
