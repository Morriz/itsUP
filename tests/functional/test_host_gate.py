#!/usr/bin/env python3

"""Process-tier acceptance for host-only runtime command gating."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ITSUP = REPO_ROOT / ".venv" / "bin" / "itsup"
VENV_PYTHON = REPO_ROOT / ".venv" / "bin" / "python"

sys.path.insert(0, str(REPO_ROOT))

from itsup.cli import HOST_ONLY, cli
from lib.host_gate import detect_lan_ip

USAGE_LABEL = "Usage:"
BYPASS_HINTS = ("bypass", "override")
DIAGNOSTIC_COMMAND = "run"
INSTALL_RUNTIME_LABEL = "make install-runtime"
EXPECTED_HOST_ONLY = frozenset({"run", "apply", "down", "dns", "proxy", "svc", "monitor"})
EXPECTED_ANYWHERE = frozenset(
    {
        "pull",
        "commit",
        "status",
        "create",
        "init",
        "validate",
        "migrate",
        "edit-secret",
        "encrypt",
        "decrypt",
        "diff-secrets",
        "sops-key",
        "projects",
    }
)
UNINSTALL_RUNTIME = REPO_ROOT / "bin" / "uninstall-runtime.sh"
LAUNCHD_LABELS = ("ai.itsup.apply", "ai.itsup.backup", "ai.itsup.bringup", "ai.itsup.api")
OFF_HOST_TEARDOWN_NOTICE = "skipping host-only 'itsup down --clean'"
BROAD_COMPOSE_INVOCATION = "compose -f"


def _write_env(root: Path, ssh_host: str | None) -> None:
    root.mkdir(parents=True, exist_ok=True)
    if ssh_host is None:
        (root / ".env").write_text("")
    else:
        (root / ".env").write_text(f"SSH_HOST={ssh_host}\n")


def _nonmatching_host() -> str:
    detected = detect_lan_ip()
    return "203.0.113.2" if detected == "203.0.113.1" else "203.0.113.1"


def _run_itsup(args: list[str], root: Path) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["ITSUP_ROOT"] = str(root)
    command = [str(ITSUP), *args]
    return subprocess.run(command, cwd=str(REPO_ROOT), env=env, capture_output=True, text=True, timeout=60, check=False)


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content)
    path.chmod(0o755)


def test_host_only_split_refuses_only_runtime_commands_off_host(tmp_path: Path) -> None:
    """Off-host help is unavailable for host-only commands and available elsewhere."""
    _write_env(tmp_path, _nonmatching_host())

    command_names = set(cli.commands)
    assert HOST_ONLY == EXPECTED_HOST_ONLY
    assert command_names - EXPECTED_HOST_ONLY == EXPECTED_ANYWHERE
    assert command_names == EXPECTED_HOST_ONLY | EXPECTED_ANYWHERE

    for command_name in sorted(command_names):
        result = _run_itsup([command_name, "--help"], tmp_path)
        output = result.stderr + result.stdout
        if command_name in EXPECTED_HOST_ONLY:
            assert result.returncode != 0, output
            assert command_name in result.stderr
            assert USAGE_LABEL not in result.stdout
        else:
            assert result.returncode == 0, output
            assert USAGE_LABEL in result.stdout


def test_host_only_command_allows_matching_host_identity(tmp_path: Path) -> None:
    """A host-only command is available when SSH_HOST matches this machine."""
    lan_ip = detect_lan_ip()
    if lan_ip is None:
        pytest.skip("LAN IP detection unavailable")

    _write_env(tmp_path, lan_ip)
    result = _run_itsup(["monitor", "--help"], tmp_path)

    assert result.returncode == 0, result.stderr
    assert USAGE_LABEL in result.stdout


def test_host_only_refusal_has_diagnostics_without_escape_hatch(tmp_path: Path) -> None:
    """The refusal names the command and does not advertise a self-grant path."""
    _write_env(tmp_path, _nonmatching_host())

    command_name = DIAGNOSTIC_COMMAND
    result = _run_itsup([command_name, "--help"], tmp_path)
    output = result.stderr + result.stdout

    assert result.returncode != 0
    assert command_name in result.stderr
    assert result.stderr.strip()
    assert all(hint not in output.lower() for hint in BYPASS_HINTS)


def test_host_only_command_refuses_unset_host_identity(tmp_path: Path) -> None:
    """A host-only command is denied when SSH_HOST is unset."""
    _write_env(tmp_path, None)

    command_name = DIAGNOSTIC_COMMAND
    result = _run_itsup([command_name, "--help"], tmp_path)

    assert result.returncode != 0
    assert command_name in result.stderr
    assert result.stderr.strip()


@pytest.mark.skipif(
    not VENV_PYTHON.exists(),
    reason="venv python absent — editable install not run",
)
def test_install_runtime_guard_refuses_off_host(tmp_path: Path) -> None:
    """The install-runtime guard exits before the shell script can mutate host state."""
    _write_env(tmp_path, _nonmatching_host())
    env = dict(os.environ)
    env["ITSUP_ROOT"] = str(tmp_path)
    env["PYTHONPATH"] = str(REPO_ROOT)

    command = [
        str(VENV_PYTHON),
        "-c",
        f"from lib.host_gate import require_host; require_host({INSTALL_RUNTIME_LABEL!r})",
    ]
    result = subprocess.run(
        command, cwd=str(REPO_ROOT), env=env, capture_output=True, text=True, timeout=60, check=False
    )

    assert result.returncode != 0
    assert INSTALL_RUNTIME_LABEL in result.stderr


@pytest.mark.functional
def test_uninstall_runtime_decommissions_stale_launchd_integration_off_host(tmp_path: Path) -> None:
    """Off-host uninstall removes stale local launchd integration without invoking `itsup down`."""
    service_dir = tmp_path / "LaunchAgents"
    service_dir.mkdir()
    install_root = tmp_path / "itsup-root"
    (install_root / ".venv" / "bin").mkdir(parents=True)
    (install_root / "proxy").mkdir()
    (install_root / "dns").mkdir()
    (install_root / "upstream").mkdir()
    (install_root / "proxy" / "docker-compose.yml").write_text("services: {}\n")
    (install_root / "dns" / "docker-compose.yml").write_text("services: {}\n")

    for label in LAUNCHD_LABELS:
        (service_dir / f"{label}.plist").write_text("<plist />\n")

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_executable(fake_bin / "uname", "#!/usr/bin/env bash\nprintf 'Darwin\\n'\n")
    _write_executable(
        fake_bin / "launchctl",
        '#!/usr/bin/env bash\nprintf \'%s\\n\' "$*" >> "${LAUNCHCTL_LOG}"\nexit 0\n',
    )
    _write_executable(
        fake_bin / "docker",
        '#!/usr/bin/env bash\nprintf \'%s\\n\' "$*" >> "${DOCKER_LOG}"\nexit 0\n',
    )
    _write_executable(fake_bin / "pgrep", "#!/usr/bin/env bash\nexit 1\n")
    _write_executable(fake_bin / "sudo", '#!/usr/bin/env bash\n"$@"\n')
    _write_executable(fake_bin / "rm", '#!/usr/bin/env bash\n/bin/rm "$@"\n')
    _write_executable(
        install_root / ".venv" / "bin" / "python",
        "#!/usr/bin/env bash\nexit 1\n",
    )
    _write_executable(
        install_root / ".venv" / "bin" / "itsup",
        "#!/usr/bin/env bash\nprintf 'unexpected itsup call\\n' >&2\nexit 99\n",
    )

    env = dict(os.environ)
    env["PATH"] = f"{fake_bin}:{env['PATH']}"
    env["ITSUP_ROOT"] = str(install_root)
    env["SERVICE_DIR"] = str(service_dir)
    env["LAUNCHCTL_LOG"] = str(tmp_path / "launchctl.log")
    env["DOCKER_LOG"] = str(tmp_path / "docker.log")

    result = subprocess.run(
        [str(UNINSTALL_RUNTIME)],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert OFF_HOST_TEARDOWN_NOTICE in result.stdout
    assert not list(service_dir.glob("ai.itsup*.plist"))
    assert BROAD_COMPOSE_INVOCATION not in (tmp_path / "docker.log").read_text()
