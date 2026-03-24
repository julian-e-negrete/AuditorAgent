from __future__ import annotations

from typing import Any, Literal

from arch_agent.models.memory import Message


class ConversationMemory:
    """Per-instance conversation memory with no shared class-level state."""

    def __init__(self) -> None:
        self._messages: list[Message] = []
        self._context: dict[str, Any] = {}

    def add_message(self, role: Literal["user", "assistant"], content: str) -> None:
        """Append a Message in insertion order."""
        self._messages.append(Message(role=role, content=content))

    def get_history(self, max_tokens: int = 4096) -> list[Message]:
        """Return the most recent messages that fit within max_tokens.

        Token estimate: len(content) // 4 per message.
        Trims from the front when budget is exceeded.
        """
        result: list[Message] = []
        budget = max_tokens
        for msg in reversed(self._messages):
            cost = len(msg.content) // 4
            if cost > budget:
                break
            budget -= cost
            result.append(msg)
        return list(reversed(result))

    def add_context(self, key: str, value: Any) -> None:
        """Store an arbitrary key-value pair."""
        self._context[key] = value

    def get_context(self) -> dict[str, Any]:
        """Return the context dict."""
        return self._context

    def clear(self) -> None:
        """Remove all messages and context."""
        self._messages.clear()
        self._context.clear()
