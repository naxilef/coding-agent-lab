"""Select a supplied eval case and repair a disposable copy."""

from collections.abc import Callable
from pathlib import Path, PureWindowsPath
from typing import Any

from core.models import RepairResult
from core.repair_agent import RepairAgent


class RepairService:
    """Connect validated project selection to injected workspace and agent factories."""

    def __init__(
        self,
        evals_root: Path,
        create_workspace: Callable[[str], Path],
        create_agent: Callable[[str, Path], RepairAgent],
        on_event: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.evals_root = Path(evals_root).resolve()
        self.create_workspace = create_workspace
        self.create_agent = create_agent
        self.on_event = on_event

    def repair(self, selected_project: str) -> RepairResult:
        """Repair one existing evals/<case> directory, never the original."""
        selected = Path(selected_project)
        windows = PureWindowsPath(selected_project)
        if selected.is_absolute() or windows.anchor or ".." in selected.parts or ".." in windows.parts:
            raise ValueError("Select a relative evals/<case> path")
        if len(selected.parts) != 2 or selected.parts[0] != "evals":
            raise ValueError("Select a project directly under evals/")
        source = self.evals_root / selected.parts[1]
        if (source.is_symlink() or not source.is_dir()
                or source.resolve().parent != self.evals_root):
            raise ValueError("Unknown project or project outside evals/")
        workspace = Path(self.create_workspace(source.name)).resolve()
        files = sorted(
            path.relative_to(workspace).as_posix()
            for path in workspace.rglob("*") if path.is_file()
        )
        agent = self.create_agent(source.name, workspace)
        if self.on_event:
            self.on_event({"event": "repair_started", "case": source.name, "workspace": str(workspace)})
        result = agent.run(source.name, files, str(workspace))
        if self.on_event:
            self.on_event(dict(result.trace[-1]))
        return result
