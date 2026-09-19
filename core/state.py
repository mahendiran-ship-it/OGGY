"""
OGGY's state machine.

A single, centralized state value that the orchestrator updates as it
works, and that the frontend polls (GET /api/state) to animate the orb.
Keeping this centralized - rather than scattering state strings through
routes/orchestrator/tools - means adding a new state later is a
one-line enum change plus one CSS rule.
"""

import threading
import time
from enum import Enum
from typing import Any, Dict, Optional


class OggyState(str, Enum):
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    RESPONDING = "responding"
    EXECUTING_TOOL = "executing_tool"
    WAITING_FOR_PERMISSION = "waiting_for_permission"
    ERROR = "error"


class StateManager:
    """Thread-safe holder for OGGY's current state, so Flask's dev server
    (which may handle requests on different threads) never reads a
    half-updated value."""

    def __init__(self):
        self._lock = threading.Lock()
        self._state = OggyState.IDLE
        self._detail: Optional[str] = None
        self._updated_at = time.time()

    def set(self, state: OggyState | str, detail: Optional[str] = None):
        with self._lock:
            if isinstance(state, str):
                state = OggyState(state)

            self._state = state
            self._detail = detail
            self._updated_at = time.time()

    def get(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "state": self._state.value,
                "detail": self._detail,
                "updated_at": self._updated_at,
            }


state_manager = StateManager()
