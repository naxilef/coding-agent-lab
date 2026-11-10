"""Assemble core repair rules with concrete scripted and sandbox adapters."""

from collections.abc import Callable
import json
from pathlib import Path
from typing import Any

from adapters.models.scripted import ScriptedClient
from adapters.models.ollama import OllamaClient
from adapters.sandbox import runner
from adapters.sandbox.repair_tools import RepairTools
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
        return RepairAgent(client, tools, on_event=on_event)

    return RepairService(runner.EVALS_ROOT, runner.create_workspace, create_agent)
