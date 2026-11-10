"""Assemble core repair rules with concrete scripted and sandbox adapters."""

from collections.abc import Callable
from dataclasses import asdict
import json
from pathlib import Path
from typing import Any

from adapters.models.scripted import ScriptedClient
from adapters.models.ollama import OllamaClient
from adapters.sandbox import runner
from adapters.sandbox.repair_tools import RepairTools
from core.models import TestResult
from core.ports import ChatClient
from core.repair_agent import RepairAgent
from core.repair_service import RepairService


# Each answer card changes only the defective expression in its case.
SCRIPTED_FIXES = {
    "arithmetic": (
        "calculator.py", "test_calculator.py",
        "return left - right", "return left + right",
    ),
    "balanced_brackets": (
        "brackets.py", "test_brackets.py",
        "            stack.pop()",
        "            if stack.pop() != pairs[character]:\n                return False",
    ),
    "median": (
        "statistics_tools.py", "test_statistics_tools.py",
        "    return ordered[middle]",
        "    if len(ordered) % 2 == 0:\n"
        "        return (ordered[middle - 1] + ordered[middle]) / 2\n"
        "    return ordered[middle]",
    ),
    "multi_function": (
        "text_tools.py", "test_text_tools.py",
        "normalize_name(name).upper()", "normalize_name(name).title()",
    ),
    "unique_words": (
        "word_tools.py", "test_word_tools.py",
        "sorted(set(text.lower().split()))",
        "list(dict.fromkeys(text.lower().split()))",
    ),
}


def scripted_replies(case: str, workspace: Path) -> list[str]:
    """Prepare separate inspection, reproduction, edit, and verification cards."""
    source, test, before, after = SCRIPTED_FIXES[case]
    content = (workspace / source).read_text(encoding="utf-8")
    if content.count(before) != 1:
        raise ValueError(f"Scripted fixture does not match the expected source: {case}")
    actions = [
        {"tool": "read_file", "path": test, "summary": "Read the tests"},
        {"tool": "read_file", "path": source, "summary": "Inspect the source"},
        {"tool": "run_tests", "summary": "Reproduce the failure"},
        {"tool": "edit_file", "path": source, "content": content.replace(before, after, 1),
         "summary": "Fix the defective expression"},
        {"tool": "run_tests", "summary": "Verify the repair"},
    ]
    return [json.dumps(action) for action in actions]


class _VisibleClient:
    """Forward model replies while leaving action validation to RepairAgent."""

    def __init__(self, client: ChatClient, emit: Callable[[dict[str, Any]], None]) -> None:
        self.client = client
        self.emit = emit
        self.decision = 0

    def chat(self, messages: list[dict[str, str]]) -> str:
        reply = self.client.chat(messages)
        self.decision += 1
        self.emit({"event": "model_response", "decision": self.decision,
                   "reply": reply})
        return reply


class _VisibleTools:
    """Forward tool observations immediately while retaining safe tool boundaries."""

    def __init__(self, tools: RepairTools, emit: Callable[[dict[str, Any]], None]) -> None:
        self.tools = tools
        self.emit = emit

    def _call(self, tool: str, *arguments: str) -> Any:
        try:
            result = getattr(self.tools, tool)(*arguments)
        except Exception as exc:
            self.emit({"event": "tool_result", "tool": tool,
                       "error": "tool_error", "message": str(exc)})
            raise
        if tool == "run_tests":
            observation = asdict(result)
        elif tool == "read_file":
            observation = {"content": result}
        else:
            observation = {"edited": arguments[0]}
        self.emit({"event": "tool_result", "tool": tool, **observation})
        return result

    def read_file(self, path: str) -> str:
        """Read through the safe workspace tools."""
        return self._call("read_file", path)

    def edit_file(self, path: str, content: str) -> None:
        """Edit through the safe workspace tools."""
        self._call("edit_file", path, content)

    def run_tests(self) -> TestResult:
        """Execute tests through the Docker-backed tools."""
        return self._call("run_tests")


def create_service(
    provider: str = "scripted",
    on_event: Callable[[dict[str, Any]], None] | None = None,
    model: str | None = None,
    temperature: float = 0.0,
) -> RepairService:
    """Wire a fresh client and workspace tools for each repair attempt."""
    if provider not in {"scripted", "ollama"}:
        raise ValueError(f"Unsupported provider: {provider}")

    def create_agent(case: str, workspace: Path) -> RepairAgent:
        client = (
            OllamaClient(model=model, temperature=temperature)
            if provider == "ollama"
            else ScriptedClient(scripted_replies(case, workspace))
        )
        tools = RepairTools(workspace)
        if on_event:
            return RepairAgent(_VisibleClient(client, on_event), _VisibleTools(tools, on_event))
        return RepairAgent(client, tools)

    return RepairService(runner.EVALS_ROOT, runner.create_workspace, create_agent, on_event)
