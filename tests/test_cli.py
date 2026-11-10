"""Check readable live output without executing fixture code."""

from types import SimpleNamespace

from adapters.models.scripted import ScriptedClient
from core.models import RepairResult, TestResult
from core.repair_agent import RepairAgent
import main


def test_cli_labels_indentation_and_final_status(monkeypatch, capsys):
    events = [
        {"event": "repair_started", "case": "arithmetic", "workspace": "/copy"},
        {"event": "model_response", "decision": 1, "action": {
            "tool": "read_file", "arguments": {"path": "calculator.py"}, "summary": "Inspect source"}},
        {"event": "tool_result", "tool": "read_file", "content": "first\nsecond\n"},
        {"event": "tool_result", "tool": "run_tests", "passed": False,
         "returncode": 1, "output": "failure\nassertion\n"},
        {"event": "tool_result", "tool": "edit_file", "edited": "calculator.py"},
        {"event": "repair_finished", "passed": True, "reason": "Verified"},
    ]

    def factory(provider, on_event, **options):
        def repair(project):
            for event in events:
                on_event(event)
                # Events appear during execution, before the result is returned.
                assert capsys.readouterr().out.startswith({
                    "repair_started": "START", "model_response": "ACTION",
                    "tool_result": "RESULT", "repair_finished": "FINISHED",
                }[event["event"]])
            return RepairResult(True, events, ["calculator.py"], "/copy", TestResult(True, "2 passed", 0))
        return SimpleNamespace(repair=repair)

    monkeypatch.setattr(main, "create_service", factory)
    assert main.main(["repair", "evals/arithmetic"]) == 0
    output = capsys.readouterr().out
    assert "Changed files:\n    calculator.py" in output
    assert "Final sandboxed test status: PASSED (exit 0)" in output
    main.print_event(events[2])
    main.print_event(events[3])
    output = capsys.readouterr().out
    assert "    first\n    second" in output
    assert "    failure\n    assertion" in output


def test_live_events_match_stored_trace_and_show_policy_errors():
    events = []
    client = ScriptedClient(['{"tool":"edit_file","path":"x","content":"y"}'])
    result = RepairAgent(client, SimpleNamespace(), on_event=events.append).run("case", [])
    assert events == result.trace
    assert events[2]["error"] == "policy_error"
    assert "Client error" in events[-1]["reason"]
    events[0]["case"] = "changed snapshot"
    assert result.trace[0]["case"] == "case"


def test_failed_cli_preserves_exit_status(monkeypatch, capsys):
    result = RepairResult(False, last_test_result=TestResult(False, "failed", 1))
    monkeypatch.setattr(main, "create_service", lambda *args, **kwargs: SimpleNamespace(repair=lambda project: result))
    assert main.main(["repair", "evals/arithmetic"]) == 1
    assert "Final sandboxed test status: FAILED (exit 1)" in capsys.readouterr().out
