"""
Conversation context.

Holds the short-term message history for the current session, separate
from persistent memory (memory/memory.py handles what survives across
sessions). Kept intentionally simple - a bounded in-memory list - since
V1 is single-user, single-session.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List

MAX_HISTORY_MESSAGES = 40


@dataclass
class ConversationContext:
    messages: List[Dict[str, Any]] = field(default_factory=list)

    def add_user_message(self, text: str):
        self.messages.append({"role": "user", "content": text})
        self._trim()

    def add_assistant_message(self, content: Any):
        self.messages.append({"role": "assistant", "content": content})
        self._trim()

    def add_tool_result(self, tool_use_id: str, content: Any, is_error: bool = False):
        self.messages.append({
            "role": "user",
            "content": [{
                "type": "tool_result",
                "tool_use_id": tool_use_id,
                "content": str(content),
                "is_error": is_error,
            }],
        })
        self._trim()

    def _trim(self):
        if len(self.messages) > MAX_HISTORY_MESSAGES:
            self.messages = self.messages[-MAX_HISTORY_MESSAGES:]

    def as_list(self) -> List[Dict[str, Any]]:
        return list(self.messages)

    def clear(self):
        self.messages = []


# Single shared session for V1 (no multi-user auth yet).
conversation = ConversationContext()
