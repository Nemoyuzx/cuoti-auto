from __future__ import annotations

import os
import plistlib
import re
import signal
import shlex
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from .config import Settings


SERVICE_LABEL = "com.nemoyu.cuoti-auto"
OPENER_LABEL = "com.nemoyu.cuoti-auto.open"
LAUNCHCTL = Path("/bin/launchctl")
OPEN = Path("/usr/bin/open")


def _require_macos() -> None:
    if sys.platform != "darwin":
        raise RuntimeError("自动常驻服务目前只支持 macOS LaunchAgent")


def _browser_url(settings: Settings) -> str:
    host = settings.host
    if host in {"0.0.0.0", "::", "[::]"}:
        host = "127.0.0.1"
    return f"http://{host}:{settings.port}"


def _launch_agent_paths() -> tuple[Path, Path]:
    root = Path.home() / "Library" / "LaunchAgents"
    return root / f"{SERVICE_LABEL}.plist", root / f"{OPENER_LABEL}.plist"


def _runtime_paths() -> dict[str, Path]:
    root = Path.home() / "Library" / "Application Support" / "cuoti-auto"
    return {
        "root": root,
        "monitor": root / "monitor.zsh",
        "launcher": root / "start-service.command",
        "supervisor": root / "supervisor.zsh",
        "opener": root / "open-when-ready.zsh",
        "pid": root / "supervisor.pid",
    }


def build_launch_agent_plists(
    settings: Settings,
    executable: Path | None = None,
    runtime_root: Path | None = None,
) -> tuple[dict[str, object], dict[str, object]]:
    """构造常驻服务与单次打开器。

    打开器不设 KeepAlive，因此服务异常重启时不会反复打开浏览器标签；
    它只会在 LaunchAgent 登录会话加载时执行一次。
    """
    del executable  # 服务由 Terminal 启动，避免 LaunchAgent 被 macOS 拒绝访问桌面目录。
    runtime_root = runtime_root or _runtime_paths()["root"]
    log_root = settings.project_root / "output" / "logs"
    environment = {
        "CUOTI_PROJECT_ROOT": str(settings.project_root),
        "CUOTI_DESKTOP": str(settings.desktop),
        "CUOTI_HOST": settings.host,
        "CUOTI_PORT": str(settings.port),
        "CUOTI_OPENAI_MODEL": settings.openai_model,
        "PATH": os.environ.get(
            "PATH",
            "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
        ),
        "PYTHONUNBUFFERED": "1",
    }
    common: dict[str, object] = {
        "WorkingDirectory": str(runtime_root),
        "EnvironmentVariables": environment,
        "LimitLoadToSessionType": "Aqua",
        "ProcessType": "Background",
        "ThrottleInterval": 5,
    }
    service = {
        **common,
        "Label": SERVICE_LABEL,
        "ProgramArguments": ["/bin/zsh", str(runtime_root / "monitor.zsh")],
        "RunAtLoad": True,
        "KeepAlive": True,
        "StandardOutPath": str(log_root / "service.log"),
        "StandardErrorPath": str(log_root / "service.error.log"),
    }
    opener = {
        **common,
        "Label": OPENER_LABEL,
        "ProgramArguments": ["/bin/zsh", str(runtime_root / "open-when-ready.zsh")],
        "RunAtLoad": True,
        "StandardOutPath": str(log_root / "opener.log"),
        "StandardErrorPath": str(log_root / "opener.error.log"),
    }
    return service, opener


def _write_plist(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", delete=False) as handle:
        temporary = Path(handle.name)
        plistlib.dump(payload, handle, sort_keys=False)
    temporary.chmod(0o644)
    temporary.replace(path)


def _write_script(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    path.chmod(0o700)


def _write_runtime_scripts(settings: Settings) -> dict[str, Path]:
    """生成不位于受保护桌面目录中的轻量启动脚本。

    macOS 会拒绝 launchd 直接读取 Desktop 下的 Python 虚拟环境和数据库。
    健康监视器因此只访问 localhost；需要拉起服务时，交由用户已授权的
    Terminal 启动后台 supervisor，无需给 Python 授予“完全磁盘访问”。
    """
    paths = _runtime_paths()
    url = shlex.quote(_browser_url(settings))
    launcher = shlex.quote(str(paths["launcher"]))
    supervisor = shlex.quote(str(paths["supervisor"]))
    pid_path = shlex.quote(str(paths["pid"]))
    executable = shlex.quote(str(settings.project_root / ".venv" / "bin" / "cuoti"))
    service_log = shlex.quote(str(settings.project_root / "output" / "logs" / "service.log"))
    service_error = shlex.quote(str(settings.project_root / "output" / "logs" / "service.error.log"))

    _write_script(paths["monitor"], f"""#!/bin/zsh
set -u
URL={url}
LAUNCHER={launcher}
while true; do
  if ! /usr/bin/curl --fail --silent --max-time 1 "$URL" >/dev/null 2>&1; then
    /usr/bin/open -g "$LAUNCHER"
    /bin/sleep 8
  else
    /bin/sleep 3
  fi
done
""")
    _write_script(paths["launcher"], f"""#!/bin/zsh
set -u
URL={url}
SUPERVISOR={supervisor}
PID_FILE={pid_path}
if /usr/bin/curl --fail --silent --max-time 1 "$URL" >/dev/null 2>&1; then
  exit 0
fi
if [ -f "$PID_FILE" ]; then
  SUPERVISOR_PID="$(/bin/cat "$PID_FILE" 2>/dev/null || true)"
  if [ -n "$SUPERVISOR_PID" ] && /bin/kill -0 "$SUPERVISOR_PID" 2>/dev/null; then
    exit 0
  fi
  /bin/rm -f "$PID_FILE"
fi
/usr/bin/nohup /bin/zsh "$SUPERVISOR" </dev/null >/dev/null 2>&1 &
exit 0
""")
    _write_script(paths["supervisor"], f"""#!/bin/zsh
set -u
URL={url}
PID_FILE={pid_path}
CUOTI={executable}
SERVICE_LOG={service_log}
SERVICE_ERROR={service_error}
echo $$ > "$PID_FILE"
trap '/bin/rm -f "$PID_FILE"' EXIT INT TERM
while true; do
  if /usr/bin/curl --fail --silent --max-time 1 "$URL" >/dev/null 2>&1; then
    /bin/sleep 3
    continue
  fi
  "$CUOTI" serve --no-open >>"$SERVICE_LOG" 2>>"$SERVICE_ERROR"
  /bin/sleep 3
done
""")
    _write_script(paths["opener"], f"""#!/bin/zsh
set -u
URL={url}
for attempt in {{1..240}}; do
  if /usr/bin/curl --fail --silent --max-time 1 "$URL" >/dev/null 2>&1; then
    exec /usr/bin/open "$URL"
  fi
  /bin/sleep 0.25
done
echo "等待服务就绪超时：$URL" >&2
exit 1
""")
    return paths


def _launchctl(*arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(LAUNCHCTL), *arguments],
        check=check,
        text=True,
        capture_output=True,
    )


def install(settings: Settings) -> tuple[Path, Path]:
    _require_macos()
    executable = settings.project_root / ".venv" / "bin" / "cuoti"
    if not executable.is_file() or not os.access(executable, os.X_OK):
        raise RuntimeError(f"未找到可执行的错题服务：{executable}")

    log_root = settings.project_root / "output" / "logs"
    log_root.mkdir(parents=True, exist_ok=True)
    runtime_paths = _write_runtime_scripts(settings)
    service_path, opener_path = _launch_agent_paths()
    service, opener = build_launch_agent_plists(settings, executable, runtime_paths["root"])
    _write_plist(service_path, service)
    _write_plist(opener_path, opener)

    domain = f"gui/{os.getuid()}"
    for label in (OPENER_LABEL, SERVICE_LABEL):
        _launchctl("bootout", f"{domain}/{label}", check=False)
    for path in (service_path, opener_path):
        _launchctl("bootstrap", domain, str(path))
    _launchctl("enable", f"{domain}/{SERVICE_LABEL}")
    _launchctl("enable", f"{domain}/{OPENER_LABEL}")
    _launchctl("kickstart", "-k", f"{domain}/{SERVICE_LABEL}")
    return service_path, opener_path


def uninstall() -> tuple[Path, Path]:
    _require_macos()
    service_path, opener_path = _launch_agent_paths()
    domain = f"gui/{os.getuid()}"
    for label in (OPENER_LABEL, SERVICE_LABEL):
        _launchctl("bootout", f"{domain}/{label}", check=False)
    pid_path = _runtime_paths()["pid"]
    try:
        pid_text = pid_path.read_text(encoding="utf-8").strip()
        if pid_text.isascii() and pid_text.isdigit():
            os.kill(int(pid_text), signal.SIGTERM)
    except (FileNotFoundError, ProcessLookupError, PermissionError):
        pass
    pid_path.unlink(missing_ok=True)
    service_path.unlink(missing_ok=True)
    opener_path.unlink(missing_ok=True)
    return service_path, opener_path


def _service_state(label: str) -> tuple[bool, str, str]:
    domain = f"gui/{os.getuid()}"
    result = _launchctl("print", f"{domain}/{label}", check=False)
    if result.returncode != 0:
        return False, "unloaded", ""
    state_match = re.search(r"\bstate = ([^\n]+)", result.stdout)
    pid_match = re.search(r"\bpid = ([0-9]+)", result.stdout)
    return True, state_match.group(1).strip() if state_match else "loaded", pid_match.group(1) if pid_match else ""


def status(settings: Settings) -> int:
    _require_macos()
    loaded, state, pid = _service_state(SERVICE_LABEL)
    endpoint_ok = endpoint_ready(_browser_url(settings), timeout=1.0)
    pid_text = f" pid={pid}" if pid else ""
    print(f"LaunchAgent: {'已加载' if loaded else '未加载'} ({state}{pid_text})")
    print(f"网页: {'可访问' if endpoint_ok else '不可访问'} ({_browser_url(settings)})")
    return 0 if loaded and endpoint_ok else 1


def endpoint_ready(url: str, timeout: float = 1.0) -> bool:
    try:
        with urlopen(url, timeout=timeout) as response:
            return 200 <= response.status < 400
    except (OSError, URLError):
        return False


def open_when_ready(settings: Settings, wait_seconds: float = 60.0) -> int:
    _require_macos()
    url = _browser_url(settings)
    deadline = time.monotonic() + wait_seconds
    while time.monotonic() < deadline:
        if endpoint_ready(url):
            return subprocess.call([str(OPEN), url])
        time.sleep(0.25)
    print(f"等待服务就绪超时：{url}", file=sys.stderr)
    return 1
