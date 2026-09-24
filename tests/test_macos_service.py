from pathlib import Path
import subprocess

from cuoti.config import Settings
from cuoti import macos_service
from cuoti.macos_service import OPENER_LABEL, SERVICE_LABEL, build_launch_agent_plists


def test_launch_agents_keep_service_alive_and_open_browser_once(tmp_path: Path) -> None:
    settings = Settings(tmp_path / "project", tmp_path / "Desktop", "127.0.0.1", 8765, "model")
    executable = settings.project_root / ".venv" / "bin" / "cuoti"
    runtime_root = tmp_path / "Application Support" / "cuoti-auto"

    service, opener = build_launch_agent_plists(settings, executable, runtime_root)

    assert service["Label"] == SERVICE_LABEL
    assert service["ProgramArguments"] == ["/bin/zsh", str(runtime_root / "monitor.zsh")]
    assert service["KeepAlive"] is True
    assert service["RunAtLoad"] is True
    assert service["EnvironmentVariables"]["CUOTI_PROJECT_ROOT"] == str(settings.project_root)
    assert service["StandardOutPath"].endswith("output/logs/service.log")

    assert opener["Label"] == OPENER_LABEL
    assert opener["ProgramArguments"] == ["/bin/zsh", str(runtime_root / "open-when-ready.zsh")]
    assert opener["RunAtLoad"] is True
    assert "KeepAlive" not in opener


def test_install_clears_persisted_disabled_state_before_bootstrap(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_root = tmp_path / "project"
    executable = project_root / ".venv" / "bin" / "cuoti"
    executable.parent.mkdir(parents=True)
    executable.write_text("#!/bin/sh\n", encoding="utf-8")
    executable.chmod(0o700)
    settings = Settings(project_root, tmp_path / "Desktop", "127.0.0.1", 8765, "model")
    runtime_root = tmp_path / "Application Support" / "cuoti-auto"
    service_path = tmp_path / "LaunchAgents" / f"{SERVICE_LABEL}.plist"
    opener_path = tmp_path / "LaunchAgents" / f"{OPENER_LABEL}.plist"
    calls: list[tuple[str, ...]] = []

    monkeypatch.setattr(macos_service, "_require_macos", lambda: None)
    monkeypatch.setattr(
        macos_service,
        "_write_runtime_scripts",
        lambda _settings: {"root": runtime_root},
    )
    monkeypatch.setattr(
        macos_service,
        "_launch_agent_paths",
        lambda: (service_path, opener_path),
    )

    def record_launchctl(*arguments: str, check: bool = True):
        del check
        calls.append(arguments)
        return subprocess.CompletedProcess(["launchctl", *arguments], 0, "", "")

    monkeypatch.setattr(macos_service, "_launchctl", record_launchctl)

    macos_service.install(settings)

    first_bootstrap = next(index for index, call in enumerate(calls) if call[0] == "bootstrap")
    enable_calls = [index for index, call in enumerate(calls) if call[0] == "enable"]
    assert len(enable_calls) == 2
    assert max(enable_calls) < first_bootstrap


def test_supervisor_ignores_mojibaked_launch_services_project_root(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_root = tmp_path / "中文项目"
    settings = Settings(project_root, tmp_path / "Desktop", "127.0.0.1", 8765, "model")
    runtime_root = tmp_path / "Application Support" / "cuoti-auto"
    runtime_paths = {
        "root": runtime_root,
        "monitor": runtime_root / "monitor.zsh",
        "launcher": runtime_root / "start-service.command",
        "supervisor": runtime_root / "supervisor.zsh",
        "opener": runtime_root / "open-when-ready.zsh",
        "pid": runtime_root / "supervisor.pid",
    }
    monkeypatch.setattr(macos_service, "_runtime_paths", lambda: runtime_paths)

    written = macos_service._write_runtime_scripts(settings)

    supervisor = written["supervisor"].read_text(encoding="utf-8")
    assert "unset CUOTI_PROJECT_ROOT" in supervisor
    assert str(project_root / ".venv" / "bin" / "cuoti") in supervisor
    assert "trap '/bin/rm -f \"$PID_FILE\"' EXIT" in supervisor
    assert "trap 'exit 0' INT TERM" in supervisor
