"""Small data containers shared by the repair workflow."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TestResult:
    """The outcome and captured output of a test run."""

    __test__ = False

    passed: bool
    output: str
    returncode: int


@dataclass
class ModelAction:
    """A requested tool call with an optional public summary."""

    tool: str
    arguments: dict[str, Any]
    summary: str | None = None


@dataclass
class RepairResult:
    """The repair outcome, trace, changed paths, and latest test result."""

    passed: bool
    trace: list[dict[str, Any]] = field(default_factory=list)
    changed_files: list[str] = field(default_factory=list)
    workspace: str = ""
    last_test_result: TestResult | None = None
