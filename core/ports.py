"""Structural interfaces for repair workflow dependencies."""

from typing import Any, Protocol

from core.models import TestResult


class ChatClient(Protocol):
    """Provide text responses for a conversation."""

    def chat(self, messages: list[dict[str, str]]) -> str:
        """Return the response to the supplied messages."""
        ...


class RepairToolsPort(Protocol):
    """Expose workspace file operations and test execution."""

    def read_file(self, path: str) -> str:
        """Read a workspace file as text."""
        ...

    def edit_file(self, path: str, content: str) -> None:
        """Write replacement text to a workspace file."""
        ...

    def run_tests(self) -> TestResult:
        """Run the workspace tests and return their outcome."""
        ...


class TraceRecorder(Protocol):
    """Optionally receive structured workflow events."""

    def record(self, event: str, payload: dict[str, Any]) -> None:
        """Record a named event and its public data."""
        ...
