"""
Structured audit logging for every tool action OGGY takes.

Deliberately named `oggy_logging` (not `logging`) so this package never
shadows Python's standard library logging module, which core/ and
tools/ also use for ordinary application logs.
"""

import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Dict, Optional

from config import config

_SECRET_KEY_PATTERN = re.compile(
    r"(api[_-]?key|token|password|secret|authorization)", re.IGNORECASE
)


def _redact(obj: Any) -> Any:
    """Recursively strip anything that looks like a secret before it is
    ever written to disk."""
    if isinstance(obj, dict):
        return {
            k: ("***REDACTED***" if _SECRET_KEY_PATTERN.search(str(k)) else _redact(v))
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_redact(v) for v in obj]
    return obj


class AuditLogger:
    def __init__(self):
        config.ensure_dirs()
        self.log_path = config.LOG_DIR / "audit.log"

        self._py_logger = logging.getLogger("oggy.audit")
        self._py_logger.setLevel(logging.INFO)
        if not self._py_logger.handlers:
            handler = logging.FileHandler(self.log_path, encoding="utf-8")
            handler.setFormatter(logging.Formatter("%(message)s"))
            self._py_logger.addHandler(handler)

            console = logging.StreamHandler()
            console.setFormatter(logging.Formatter("[OGGY] %(message)s"))
            self._py_logger.addHandler(console)

    def log_tool_call(
        self,
        request: str,
        tool_name: str,
        arguments: Dict[str, Any],
        permission_level: str,
        approval_status: str,
        result: Optional[Any] = None,
        error: Optional[str] = None,
    ):
        entry = {
            "timestamp": time.time(),
            "type": "tool_call",
            "user_request": request,
            "tool": tool_name,
            "arguments": _redact(arguments),
            "permission_level": permission_level,
            "approval_status": approval_status,  # auto | approved | denied | pending
            "result": _redact(result) if result is not None else None,
            "error": error,
        }
        self._py_logger.info(json.dumps(entry))

    def log_event(self, event_type: str, **fields):
        entry = {"timestamp": time.time(), "type": event_type, **_redact(fields)}
        self._py_logger.info(json.dumps(entry))


audit_logger = AuditLogger()
