"""Contracts for installed runtime service templates."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SYSTEMD_DIR = REPO_ROOT / "samples" / "systemd"
ROOT_USER_DIRECTIVE = "User=root"
NO_BYTECODE_DIRECTIVE = "Environment=PYTHONDONTWRITEBYTECODE=1"
PACKAGED_ENTRYPOINT = "{{ROOT}}/.venv/bin/itsup"
HANDWRITTEN_ENTRYPOINT = "bin/itsup"


def test_root_backup_cannot_poison_the_user_owned_virtualenv() -> None:
    """The root backup process must never create root-owned bytecode in .venv."""
    service = (SYSTEMD_DIR / "itsup-backup.service").read_text(encoding="utf-8")

    assert ROOT_USER_DIRECTIVE in service
    assert NO_BYTECODE_DIRECTIVE in service


def test_runtime_services_use_the_packaged_cli_entrypoint() -> None:
    """Non-backup runtime services invoke the console script minted by uv."""
    for name in ("itsup-bringup.service", "itsup-apply.service"):
        service = (SYSTEMD_DIR / name).read_text(encoding="utf-8")
        assert PACKAGED_ENTRYPOINT in service
        assert HANDWRITTEN_ENTRYPOINT not in service.replace(".venv/bin/itsup", "")
