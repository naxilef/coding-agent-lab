"""Run a selected supplied repair case from the terminal."""

import argparse
import sys
from textwrap import indent

from bootstrap import create_service
from adapters.trace_format import format_event


def print_event(event: dict) -> None:
    """Print one formatted event immediately."""
    text = format_event(event)
    if text:
        print(text, flush=True)


def main(argv: list[str] | None = None) -> int:
    """Print live repair events and return a failing status unless verified."""
    parser = argparse.ArgumentParser(description="Repair a supplied eval case in Docker")
    commands = parser.add_subparsers(dest="command", required=True)
    repair = commands.add_parser("repair", help="Repair a disposable copy of an eval case")
    repair.add_argument("project", help="Selected evals/<case> path")
    repair.add_argument("--provider", choices=["scripted", "ollama"], default="scripted")
    repair.add_argument("--model", help="Ollama model (defaults to OLLAMA_MODEL or qwen2.5-coder:7b)")
    repair.add_argument("--temperature", type=float, default=0.0, help="Ollama sampling temperature")
    commands.add_parser("ui", help="Open the local scripted repair page")
    args = parser.parse_args(argv)

    if args.command == "ui":
        from adapters.gradio_ui import create_demo

        create_demo(create_service("scripted")).launch(server_name="127.0.0.1", share=False)
        return 0

    try:
        result = create_service(
            args.provider, print_event, model=args.model, temperature=args.temperature
        ).repair(args.project)
    except Exception as exc:
        print(f"FINISHED FAILED\n{indent(str(exc), '    ')}", file=sys.stderr, flush=True)
        return 1
    print("\nChanged files:")
    for path in result.changed_files:
        print(f"    {path}")
    if not result.changed_files:
        print("    (none)")
    tests = result.last_test_result
    if tests is None:
        print("Final sandboxed test status: NOT RUN")
    else:
        status = "PASSED" if tests.passed else "FAILED"
        print(f"Final sandboxed test status: {status} (exit {tests.returncode})")
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
