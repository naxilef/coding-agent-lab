"""Unit checks for workspace boundaries and Docker delegation."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from adapters.sandbox import runner
from adapters.sandbox.repair_tools import RepairTools, safe_path
from core.models import TestResult


def test_read_file(tmp_path):
    (tmp_path / "sample.txt").write_text("hello café", encoding="utf-8")
    assert RepairTools(tmp_path).read_file("sample.txt") == "hello café"


@pytest.mark.parametrize("requested", ["../secret", "nested/../../secret", "C:\\secret", "/secret"])
def test_reject_unsafe_paths(tmp_path, requested):
    with pytest.raises(ValueError):
        safe_path(tmp_path, requested)


def test_reject_absolute_path(tmp_path):
    with pytest.raises(ValueError):
        safe_path(tmp_path, str(tmp_path / "sample.txt"))


def test_edit_saved_and_recorded_once(tmp_path):
    tools = RepairTools(tmp_path)
    tools.edit_file("sample.txt", "café")
    tools.edit_file("./sample.txt", "updated café")
    assert (tmp_path / "sample.txt").read_text(encoding="utf-8") == "updated café"
    assert tools.changed_files == ["sample.txt"]


def test_run_tests_delegates(tmp_path, monkeypatch):
    expected = TestResult(True, "1 passed", 0)
    calls = []

    def fake_runner(workspace):
        calls.append(workspace)
        return expected

    def forbid_process(*args, **kwargs):
        pytest.fail("RepairTools must delegate without launching a process")

    monkeypatch.setattr(runner, "run_tests", fake_runner)
    monkeypatch.setattr(runner.subprocess, "run", forbid_process)
    assert RepairTools(tmp_path).run_tests() is expected
    assert calls == [tmp_path.resolve()]


def test_runner_launches_only_restricted_docker(tmp_path, monkeypatch):
    calls = []

    def fake_process(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=1, stdout="1 failed")

    monkeypatch.setattr(runner.subprocess, "run", fake_process)
    assert runner.run_tests(tmp_path) == TestResult(False, "1 failed", 1)
    command, options = calls[0]
    assert command[:3] == ["docker", "run", "--rm"]
    assert command[command.index("--network") + 1] == "none"
    assert command.count("--mount") == 1
    assert "--read-only" in command
    assert command[command.index("--tmpfs") + 1] == (
        "/tmp:rw,noexec,nosuid,size=64m,mode=1777"
    )
    assert command[command.index("--mount") + 1] == (
        f"type=bind,source={tmp_path.resolve()},target=/workspace,readonly"
    )
    assert command[-6:] == ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider"]
    assert options.get("shell", False) is False


def test_workspace_copy_uses_home_cache(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    evals = tmp_path / "evals"
    case = evals / "example"
    case.mkdir(parents=True)
    (case / "sample.txt").write_text("original", encoding="utf-8")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setattr(runner, "EVALS_ROOT", evals)
    first = runner.create_workspace("example")
    second = runner.create_workspace("example")
    assert first != second
    assert first.is_relative_to(home / ".cache" / "coding-agent-lab")
    (first / "sample.txt").write_text("edited", encoding="utf-8")
    assert (case / "sample.txt").read_text(encoding="utf-8") == "original"
