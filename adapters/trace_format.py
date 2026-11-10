"""Shared human-readable trace formatting for terminal and browser views."""

from textwrap import indent


def format_event(event: dict) -> str:
    """Format one trace event without changing its stored representation."""
    kind = event["event"]
    lines = []
    if kind == "repair_started":
        lines = [f"START  Repair {event['case']}", f"    Workspace: {event['workspace']}"]
    elif kind == "model_response":
        label = f"ACTION {event['decision']}"
        if "error" in event:
            lines = [f"{label}  Invalid model reply", indent(event["error"], "    ")]
        else:
            action = event["action"]
            path = action["arguments"].get("path")
            detail = action["tool"] + (f"({path})" if path else "()")
            summary = " ".join((action.get("summary") or "").split())
            lines = [f"{label}  {detail}" + (f" - {summary}" if summary else "")]
    elif kind == "tool_result":
        tool = event["tool"]
        if "error" in event:
            lines = [f"RESULT {tool}: ERROR ({event['error']})",
                     indent(event.get("message", ""), "    ")]
        elif tool == "run_tests":
            status = "PASSED" if event["passed"] else "FAILED"
            lines = [f"RESULT Sandboxed tests: {status} (exit {event['returncode']})"]
            if event["output"]:
                lines.append(indent(event["output"].rstrip(), "    ", lambda line: True))
        elif tool == "read_file":
            lines = ["RESULT File read", indent(event["content"].rstrip(), "    ", lambda line: True)]
        elif tool == "edit_file":
            lines = [f"RESULT Saved copied workspace file: {event['edited']}"]
    elif kind == "repair_finished":
        status = "SUCCESS" if event["passed"] else "FAILED"
        lines = [f"FINISHED {status}", indent(event["reason"], "    ")]
    return "\n".join(lines)


