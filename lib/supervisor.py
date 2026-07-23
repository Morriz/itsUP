"""Platform-native control for itsUP's supervised daemons."""

import os
import platform
import re
import subprocess
from enum import StrEnum
from pathlib import Path

from lib.paths import root


class Unit(StrEnum):
    """The fixed set of daemon units itsUP owns."""

    API = "itsup-api"
    MONITOR = "itsup-monitor"


def supports(unit: Unit) -> bool:
    """Return whether this platform can supervise ``unit``."""
    return not (unit is Unit.MONITOR and platform.system() == "Darwin")


def _require_supported(unit: Unit) -> None:
    if not supports(unit):
        raise RuntimeError("The container security monitor is supported on Linux only")


def _launchd_domain() -> str:
    return f"gui/{os.getuid()}"


def _launchd_target() -> str:
    return f"{_launchd_domain()}/ai.itsup.api"


def _launchd_plist() -> Path:
    return root() / "samples" / "launchd" / "ai.itsup.api.plist"


def _systemd_unit(unit: Unit) -> str:
    return f"{unit}.service"


def start(unit: Unit) -> None:
    """Start a daemon without replacing a running instance."""
    _require_supported(unit)
    system = platform.system()
    if system == "Linux":
        # systemctl is the only Linux interface for named system-unit control.
        subprocess.run(["sudo", "systemctl", "start", _systemd_unit(unit)], check=True)
        return
    if system == "Darwin":
        # launchctl print is the native registration and liveness inspection surface.
        status = subprocess.run(["launchctl", "print", _launchd_target()], check=False, capture_output=True, text=True)
        if status.returncode != 0:
            # launchctl bootstrap is the only way to register and start an unloaded agent.
            subprocess.run(["launchctl", "bootstrap", _launchd_domain(), str(_launchd_plist())], check=True)
        elif not re.search(r"^\s*pid = \d+$", status.stdout, re.MULTILINE):
            # launchctl kickstart starts a registered agent that has no live process.
            subprocess.run(["launchctl", "kickstart", _launchd_target()], check=True)
        return
    raise RuntimeError(f"Unsupported platform for daemon supervision: {system}")


def stop(unit: Unit) -> None:
    """Stop a daemon and leave it inactive."""
    _require_supported(unit)
    system = platform.system()
    if system == "Linux":
        # systemctl is the only Linux interface for named system-unit control.
        subprocess.run(["sudo", "systemctl", "stop", _systemd_unit(unit)], check=True)
        return
    if system == "Darwin":
        # launchctl bootout is the native way to stop and unregister an agent.
        subprocess.run(["launchctl", "bootout", _launchd_domain(), str(_launchd_plist())], check=True)
        return
    raise RuntimeError(f"Unsupported platform for daemon supervision: {system}")


def restart(unit: Unit) -> None:
    """Replace a daemon process while preserving its loaded definition."""
    _require_supported(unit)
    system = platform.system()
    if system == "Linux":
        # systemctl is the only Linux interface for named system-unit control.
        subprocess.run(["sudo", "systemctl", "restart", _systemd_unit(unit)], check=True)
        return
    if system == "Darwin":
        # launchctl owns a safe in-place restart of an already-registered agent.
        subprocess.run(["launchctl", "kickstart", "-k", _launchd_target()], check=True)
        return
    raise RuntimeError(f"Unsupported platform for daemon supervision: {system}")


def write_monitor_flags(flags: list[str]) -> Path:
    """Persist monitor startup flags for the systemd unit's EnvironmentFile."""
    path = root() / ".itsup-monitor.env"
    path.write_text(f"MONITOR_FLAGS={' '.join(flags)}\n")
    return path
