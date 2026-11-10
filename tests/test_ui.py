"""Check download postprocessing with Gradio's launched-app path checks."""

import asyncio
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZipFile

from gradio.context import LocalContext

from adapters.gradio_ui import create_demo
from core.models import RepairResult, TestResult


def test_launched_ui_returns_results_and_download(tmp_path):
    """A browser response can serve the ZIP without exposing the workspace."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "calculator.py").write_text("fixed source", encoding="utf-8")
    calls = []

    def repair(selected):
        calls.append(selected)
        return RepairResult(
            True, [{"event": "repair_finished", "passed": True}],
            ["calculator.py"], str(workspace), TestResult(True, "2 passed", 0),
        )

    demo = create_demo(SimpleNamespace(repair=repair))

    async def invoke():
        demo.has_launched = True
        token = LocalContext.blocks.set(demo)
        try:
            return await demo.process_api(0, ["arithmetic"], state=None)
        finally:
            LocalContext.blocks.reset(token)

    result = asyncio.run(invoke())["data"]
    assert calls == ["evals/arithmetic"]
    assert "repair_finished" in result[0]
    assert "calculator.py\nfixed source" in result[1]
    assert "2 passed" in result[2]
    archive = Path(result[3]["path"])
    assert archive.is_file()
    assert not archive.is_relative_to(workspace)
    with ZipFile(archive) as bundle:
        assert bundle.namelist() == ["calculator.py"]
        assert bundle.read("calculator.py").decode("utf-8") == "fixed source"
