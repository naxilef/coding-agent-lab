"""Restrict repair operations to files in one copied workspace."""

from pathlib import Path, PureWindowsPath

from adapters.sandbox import runner
from core.models import TestResult


def safe_path(workspace: str | Path, requested_path: str) -> Path:
    """Resolve a relative path, rejecting traversal and escaping symlinks."""
    root = Path(workspace).resolve(strict=True)
    relative = Path(requested_path)
    windows = PureWindowsPath(requested_path)
    if (relative.is_absolute() or windows.anchor
            or ".." in relative.parts or ".." in windows.parts):
        raise ValueError("Path must be relative and inside the workspace")
    resolved = (root / relative).resolve()
    if not resolved.is_relative_to(root):
        raise ValueError("Path escapes the workspace")
    return resolved


class RepairTools:
    """Provide file reads, edits, and Docker-backed tests for one workspace."""

    def __init__(self, workspace: str | Path) -> None:
        self.workspace = Path(workspace).resolve(strict=True)
        self.changed_files: list[str] = []

    def read_file(self, path: str) -> str:
        """Read a workspace file using UTF-8."""
        return safe_path(self.workspace, path).read_text(encoding="utf-8")

    def edit_file(self, path: str, content: str) -> None:
        """Save UTF-8 text and record each changed relative path once."""
        target = safe_path(self.workspace, path)
        if target.exists() and target.read_text(encoding="utf-8") == content:
            return
        target.write_text(content, encoding="utf-8")
        relative = target.relative_to(self.workspace).as_posix()
        if relative not in self.changed_files:
            self.changed_files.append(relative)

    def run_tests(self) -> TestResult:
        """Delegate test execution to the Docker runner."""
        return runner.run_tests(self.workspace)
