from pathlib import Path

from cuoti.config import Settings
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
