"""Host-identity gate for runtime-mutating operations."""

import socket
import sys

from lib.paths import root
from lib.sops import load_env_file


def detect_lan_ip() -> str | None:
    """Return this machine's LAN source IP for the default route."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            # UDP connect sets the default-route source address without sending packets.
            probe.connect(("8.8.8.8", 80))
            return str(probe.getsockname()[0])
    except OSError:
        return None


def configured_host() -> str | None:
    """Return SSH_HOST from the install root's .env file."""
    value = load_env_file(root() / ".env").get("SSH_HOST")
    if value is None:
        return None

    stripped = value.strip()
    return stripped or None


def _host_identity() -> tuple[str | None, str | None]:
    try:
        return configured_host(), detect_lan_ip()
    except Exception:  # pylint: disable=broad-exception-caught
        # This is the fail-closed security seam: any identity lookup fault denies.
        return None, None


def is_host() -> bool:
    """Return True only when configured SSH_HOST matches this machine's LAN IP."""
    configured, detected = _host_identity()
    return configured is not None and detected is not None and configured == detected


def require_host(command_label: str) -> None:
    """Exit when the current machine is not the configured container host."""
    if is_host():
        return

    configured, detected = _host_identity()
    print(
        f"Refusing {command_label}: this command runs only on the container host.\n"
        f"Configured SSH_HOST: {configured or '<unset>'}\n"
        f"Detected LAN IP: {detected or '<unavailable>'}",
        file=sys.stderr,
    )
    sys.exit(1)
