"""Copy evaluation cases and execute their tests only in Docker."""

from pathlib import Path
import shutil
import subprocess
import tempfile
from uuid import uuid4

from core.models import TestResult


EVALS_ROOT = Path(__file__).resolve().parents[2] / "evals"
IMAGE = "coding-agent-lab-runner"


def create_workspace(case: str) -> Path:
    """Copy one named eval case into a disposable home-directory workspace."""
    if not case or Path(case).name != case or case in {".", ".."}:
        raise ValueError("Expected a single eval case name")
    source = EVALS_ROOT / case
    if source.is_symlink() or not source.is_dir():
        raise ValueError("Unknown eval case")
    if any(path.is_symlink() for path in source.rglob("*")):
        raise ValueError("Eval cases must not contain symbolic links")
    cache = Path.home() / ".cache" / "coding-agent-lab"
    cache.mkdir(parents=True, exist_ok=True)
    if not cache.resolve().is_relative_to(Path.home().resolve()):
        raise ValueError("Workspace cache must remain inside the home directory")
    workspace = Path(tempfile.mkdtemp(prefix=f"{case}-", dir=cache))
    try:
        shutil.copytree(source, workspace, dirs_exist_ok=True)
        workspace.chmod(0o755)
    except Exception:
        shutil.rmtree(workspace)
        raise
    return workspace


def run_tests(workspace: str | Path) -> TestResult:
    """Run copied project tests in a networkless, read-only Docker container."""
    workspace = Path(workspace).resolve(strict=True)
    if not workspace.is_dir():
        raise ValueError("Workspace must be a directory")
    name = f"coding-agent-lab-{uuid4().hex}"
    command = [
        "docker", "run", "--rm", "--name", name,
        "--network", "none", "--read-only",
        "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m,mode=1777",
        "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "--pids-limit", "128", "--memory", "256m", "--cpus", "1",
        "--mount", f"type=bind,source={workspace},target=/workspace,readonly",
        "--workdir", "/workspace", IMAGE,
        "python", "-m", "pytest", "-q", "-p", "no:cacheprovider",
    ]
    try:
        result = subprocess.run(
            command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", timeout=60,
            check=False,
        )
    except subprocess.TimeoutExpired:
        subprocess.run(
            ["docker", "rm", "--force", name], capture_output=True,
            timeout=15, check=False,
        )
        return TestResult(False, "Docker test run timed out after 60 seconds", 124)
    except OSError as exc:
        return TestResult(False, f"Unable to start Docker: {exc}", 127)
    return TestResult(result.returncode == 0, result.stdout, result.returncode)
