"""Validate model decisions and control an eight-decision repair attempt."""

from dataclasses import asdict
from collections.abc import Callable
from copy import deepcopy
import json
from typing import Any

from core.models import ModelAction, RepairResult, TestResult
from core.ports import ChatClient, RepairToolsPort
from core.prompts import repair_request, system_instruction, tool_result_message


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Reject duplicate JSON keys instead of silently replacing them."""
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError(f"Invalid JSON constant: {value}")


def _parse_action(raw: str) -> ModelAction:
    """Accept exactly one object with the selected tool's string fields."""
    if not isinstance(raw, str):
        raise ValueError("Reply must be a JSON string")
    data = json.loads(
        raw, object_pairs_hook=_unique_object, parse_constant=_reject_constant
    )
    if not isinstance(data, dict):
        raise ValueError("Reply must be one JSON object")
    tool = data.get("tool")
    required = {
        "read_file": {"tool", "path"},
        "edit_file": {"tool", "path", "content"},
        "run_tests": {"tool"},
    }
    if not isinstance(tool, str) or tool not in required:
        raise ValueError("Unknown tool")
    if not required[tool] <= data.keys():
        raise ValueError("Missing required action fields")
    if data.keys() - (required[tool] | {"summary"}):
        raise ValueError("Unexpected action fields")
    if any(not isinstance(value, str) for value in data.values()):
        raise ValueError("Action fields must be strings")
    if "path" in data and not data["path"].strip():
        raise ValueError("Path must not be empty")
    return ModelAction(
        tool, {key: data[key] for key in ("path", "content") if key in data},
        data.get("summary"),
    )


class RepairAgent:
    """Coordinate chat and permitted tools without executing project code."""

    def __init__(
        self, client: ChatClient, tools: RepairToolsPort,
        on_event: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.client = client
        self.tools = tools
        self.on_event = on_event

    def _emit(self, event: dict[str, Any]) -> None:
        """Forward a snapshot without exposing the stored trace to mutation."""
        if self.on_event is not None:
            self.on_event(deepcopy(event))

    def run(
        self, case_name: str, relative_files: list[str], workspace: str = ""
    ) -> RepairResult:
        """Attempt a repair, returning its evidence and outcome on every exit."""
        messages = [
            {"role": "system", "content": system_instruction()},
            {"role": "user", "content": repair_request(case_name, relative_files)},
        ]
        trace: list[dict[str, Any]] = [
            {"event": "repair_started", "case": case_name, "workspace": str(workspace)}
        ]
        changed_files: list[str] = []
        latest: TestResult | None = None
        read_observed = False
        failure_observed = False
        edited = False
        self._emit(trace[0])

        def finish(passed: bool, reason: str) -> RepairResult:
            trace.append({"event": "repair_finished", "passed": passed, "reason": reason})
            self._emit(trace[-1])
            return RepairResult(passed, trace, changed_files, str(workspace), latest)

        def observe(tool: str, observation: dict[str, Any]) -> None:
            trace.append({"event": "tool_result", "tool": tool, **observation})
            self._emit(trace[-1])
            messages.append({
                "role": "user", "content": tool_result_message(tool, observation)
            })

        for decision in range(1, 9):
            try:
                raw = self.client.chat([dict(message) for message in messages])
            except Exception as exc:
                return finish(False, f"Client error: {exc}")
            # Store only validated public action data, never unsolicited prose.
            response: dict[str, Any] = {"event": "model_response", "decision": decision}
            trace.append(response)
            try:
                action = _parse_action(raw)
            except (ValueError, TypeError, RecursionError) as exc:
                response["error"] = f"Invalid reply: {exc}"
                self._emit(response)
                return finish(False, f"Invalid reply: {exc}")
            response["action"] = asdict(action)
            self._emit(response)
            messages.append({"role": "assistant", "content": raw})

            if action.tool == "edit_file" and not (read_observed and failure_observed):
                observe(action.tool, {
                    "error": "policy_error",
                    "message": "An edit requires a successful read_file and a failing run_tests observation first.",
                })
                continue

            try:
                if action.tool == "read_file":
                    content = self.tools.read_file(action.arguments["path"])
                    observation = {"content": content}
                    read_observed = True
                elif action.tool == "edit_file":
                    self.tools.edit_file(action.arguments["path"], action.arguments["content"])
                    edited = True
                    path = action.arguments["path"]
                    if path not in changed_files:
                        changed_files.append(path)
                    observation = {"edited": path}
                else:
                    result = self.tools.run_tests()
                    if not isinstance(result, TestResult):
                        raise TypeError("run_tests must return TestResult")
                    latest = result
                    observation = asdict(result)
                    if not result.passed:
                        failure_observed = True
            except Exception as exc:
                observe(action.tool, {"error": "tool_error", "message": str(exc)})
                continue

            observe(action.tool, observation)
            if action.tool == "run_tests" and latest is not None and latest.passed:
                if edited:
                    return finish(True, "Repair verified by passing tests after an edit")
                return finish(False, "No reproducible bug: baseline tests passed before any edit")

        return finish(False, "Eight-decision budget exhausted")
