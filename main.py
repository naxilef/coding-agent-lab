"""Run a selected supplied repair case from the terminal."""

import argparse
from dataclasses import asdict
import json
import sys

from bootstrap import create_service


def main(argv: list[str] | None = None) -> int:
    """Print live repair events and return a failing status unless verified."""
    parser = argparse.ArgumentParser(description="Repair a supplied eval case in Docker")
    commands = parser.add_subparsers(dest="command", required=True)
    repair = commands.add_parser("repair", help="Repair a disposable copy of an eval case")
    repair.add_argument("project", help="Selected evals/<case> path")
    repair.add_argument("--provider", choices=["scripted"], default="scripted")
    args = parser.parse_args(argv)

    def print_event(event: dict) -> None:
        print(json.dumps(event, ensure_ascii=False), flush=True)

    try:
        result = create_service(args.provider, print_event).repair(args.project)
    except Exception as exc:
        print(f"Repair failed: {exc}", file=sys.stderr)
        return 1
    print("Changed relative files: " + json.dumps(result.changed_files))
    print("Final sandboxed test result: " + json.dumps(
        asdict(result.last_test_result) if result.last_test_result is not None else None,
        ensure_ascii=False,
    ))
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
