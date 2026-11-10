"""Present the existing repair service and its disposable workspace results."""

import json
import os
from pathlib import Path
import tempfile
from zipfile import ZIP_DEFLATED, ZipFile

os.environ["GRADIO_ANALYTICS_ENABLED"] = "False"

import gradio as gr


CASES = ["arithmetic", "balanced_brackets", "median", "multi_function", "unique_words"]


def _workspace_file(workspace: Path, relative: str) -> Path:
    """Resolve a result file without allowing downloads outside the workspace."""
    path = (workspace / relative).resolve(strict=True)
    if Path(relative).is_absolute() or not path.is_relative_to(workspace):
        raise ValueError("Result file escapes the repaired workspace")
    return path


def _repair(service, case: str) -> tuple[str, str, str, str | None]:
    """Call the service once and format its trace, changed text, tests, and ZIP."""
    if case not in CASES:
        return "Unknown case", "", "", None
    try:
        result = service.repair(f"evals/{case}")
        trace = "\n".join(json.dumps(event, ensure_ascii=False) for event in result.trace)
        workspace = Path(result.workspace).resolve(strict=True)
        changed = "\n\n".join(
            f"{relative}\n{_workspace_file(workspace, relative).read_text(encoding='utf-8')}"
            for relative in result.changed_files
        ) or "No changed files."
        tests = result.last_test_result
        output = (
            f"Passed: {tests.passed}\nReturn code: {tests.returncode}\n\n{tests.output}"
            if tests is not None else "No sandboxed test result."
        )
        download_dir = Path(tempfile.mkdtemp(prefix="coding-agent-lab-download-"))
        archive = download_dir / f"{workspace.name}.zip"
        with ZipFile(archive, "w", compression=ZIP_DEFLATED) as bundle:
            for path in sorted(workspace.rglob("*")):
                if path.is_symlink():
                    raise ValueError("Workspace ZIP must not contain symbolic links")
                if path.is_file():
                    relative = path.relative_to(workspace).as_posix()
                    bundle.write(_workspace_file(workspace, relative), arcname=relative)
        return trace, changed, output, str(archive)
    except Exception as exc:
        return f"Repair error: {exc}", "", "", None


def create_demo(service=None) -> gr.Blocks:
    """Build a local page, defaulting to the existing scripted repair service."""
    if service is None:
        from bootstrap import create_service

        service = create_service("scripted")

    with gr.Blocks(title="Python Repair Lab", analytics_enabled=False) as demo:
        gr.Markdown("# Python Repair Lab\nChoose a supplied case and run its scripted repair.")
        case = gr.Dropdown(choices=CASES, value="arithmetic", label="Case", allow_custom_value=False)
        start = gr.Button("Start repair", variant="primary")
        trace = gr.Textbox(label="Visible trace", lines=14, interactive=False)
        changed = gr.Textbox(label="Changed relative files and text", lines=12, interactive=False)
        tests = gr.Textbox(label="Final sandboxed test output", lines=8, interactive=False)
        download = gr.File(label="Repaired workspace ZIP", interactive=False)
        start.click(
            fn=lambda selected: _repair(service, selected),
            inputs=[case], outputs=[trace, changed, tests, download],
            concurrency_limit=1,
        )
    return demo
