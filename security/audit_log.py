"""
Thin re-export so security/ has an obvious home for "what did OGGY do"
even though the actual logger implementation lives in oggy_logging/
(kept as its own top-level package so it never collides with Python's
built-in `logging` module).
"""

from oggy_logging.logger import audit_logger  # noqa: F401
