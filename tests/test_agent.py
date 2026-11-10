"""Exercise the repair controller using prepared replies and fake tools."""

import json

import pytest

from adapters.models.scripted import ScriptedClient
from core.models import RepairResult, TestResult
from core.repair_agent import RepairAgent


def action(tool, **fields):
    return json.dumps({"tool": tool, **fields})


READ = action("read_file", path="calculator.py")
TEST = action("run_tests")
EDIT = action("edit_file", path="calculator.py", content="fixed")


class FakeTools:
    """Record calls without running project code or starting processes."""

    def __init__(self, results=()):
        self.results = iter(results)
        self.calls = []

    def read_file(self, path):
        self.calls.append(("read_file", path))
        if path == "missing.py":
            raise FileNotFoundError(path)
        return "buggy source"

    def edit_file(self, path, content):
        self.calls.append(("edit_file", path, content))

    def run_tests(self):
        self.calls.append(("run_tests",))
        return next(self.results)


class RecordingClient(ScriptedClient):
    """Capture conversation snapshots while returning scripted replies."""

    def __init__(self, replies):
        super().__init__(replies)
        self.conversations = []

    def chat(self, messages):
        self.conversations.append([dict(message) for message in messages])
        return super().chat(messages)


def run(replies, tools):
    client = RecordingClient(replies)
    result = RepairAgent(client, tools).run("arithmetic", ["calculator.py"], "/workspace")
    return result, client


def test_successful_repair_and_conversation():
    final = TestResult(True, "passed", 0)
    tools = FakeTools([TestResult(False, "failed", 1), final])
    result, client = run([READ, TEST, EDIT, TEST], tools)
    assert result.passed
    assert result.last_test_result is final
    assert result.changed_files == ["calculator.py"]
    assert result.workspace == "/workspace"
    assert [call[0] for call in tools.calls] == ["read_file", "run_tests", "edit_file", "run_tests"]
    assert [entry["event"] for entry in result.trace] == (
        ["repair_started"] + ["model_response", "tool_result"] * 4 + ["repair_finished"]
    )
    assert [message["role"] for message in client.conversations[-1]] == (
        ["system", "user"] + ["assistant", "user"] * 3
    )
    assert "arithmetic" in client.conversations[0][1]["content"]


@pytest.mark.parametrize("reply", [
    "not JSON", "```json\n{}\n```", "[]", "{}", '{"tool":',
    TEST + TEST, "Here is the action: " + TEST,
    '{"tool":"run_tests","tool":"run_tests"}',
    action("shell"), action("read_file"), action("edit_file", path="x"),
    action("run_tests", path="x"), action("read_file", path=12),
    action("run_tests", summary=None), action("run_tests", extra=float("nan")),
])
def test_invalid_reply_calls_no_tool(reply):
    tools = FakeTools()
    result, _ = run([reply], tools)
    assert not result.passed
    assert tools.calls == []
    assert "Invalid reply" in result.trace[-1]["reason"]


def test_early_edit_is_visible_and_can_recover():
    tools = FakeTools([TestResult(False, "failed", 1), TestResult(True, "passed", 0)])
    result, client = run([READ, EDIT, TEST, EDIT, TEST], tools)
    assert result.passed
    assert [call[0] for call in tools.calls].count("edit_file") == 1
    assert "policy_error" in client.conversations[2][-1]["content"]
    assert client.conversations[2][-2] == {"role": "assistant", "content": EDIT}


def test_failure_without_read_does_not_allow_edit():
    tools = FakeTools([TestResult(False, "failed", 1)])
    result, _ = run([TEST, EDIT], tools)
    assert not result.passed
    assert tools.calls == [("run_tests",)]
    assert any(entry.get("error") == "policy_error" for entry in result.trace)


def test_budget_exhaustion():
    tools = FakeTools()
    result, client = run([READ] * 9, tools)
    assert not result.passed
    assert len(client.conversations) == len(tools.calls) == 8
    assert "budget exhausted" in result.trace[-1]["reason"]


def test_passing_baseline_is_not_a_repair():
    baseline = TestResult(True, "passed", 0)
    tools = FakeTools([baseline])
    result, client = run([TEST, EDIT], tools)
    assert not result.passed
    assert result.last_test_result is baseline
    assert result.changed_files == []
    assert len(client.conversations) == 1
    assert "No reproducible bug" in result.trace[-1]["reason"]


def test_exhausted_client_returns_result():
    result, _ = run([], FakeTools())
    assert isinstance(result, RepairResult)
    assert not result.passed
    assert "Client error" in result.trace[-1]["reason"]


def test_tool_error_is_visible_and_does_not_satisfy_read_policy():
    tools = FakeTools([TestResult(False, "failed", 1)])
    result, client = run([action("read_file", path="missing.py"), TEST, EDIT], tools)
    assert not result.passed
    assert "tool_error" in client.conversations[1][-1]["content"]
    assert not any(call[0] == "edit_file" for call in tools.calls)


def test_evidence_resets_between_attempts():
    tools = FakeTools([TestResult(False, "failed", 1)])
    agent = RepairAgent(ScriptedClient([READ, TEST] + [READ] * 6 + [EDIT]), tools)
    agent.run("first", ["calculator.py"])
    result = agent.run("second", ["calculator.py"])
    assert not result.passed
    assert any(entry.get("error") == "policy_error" for entry in result.trace)
    assert not any(call[0] == "edit_file" for call in tools.calls)
