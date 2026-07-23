import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO_ROOT / "bin" / "backup.py"
SPEC_ID = "project/spec/feature/operations/backup-safe-invocation"


def _run_probe(root: Path, cwd: Path, argument: str) -> subprocess.CompletedProcess[str]:
    environment = dict(os.environ)
    environment["ITSUP_ROOT"] = str(root)

    return subprocess.run(
        [sys.executable, str(SCRIPT), argument],
        cwd=cwd,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


@pytest.mark.functional
@pytest.mark.spec(SPEC_ID, "UC-BSI1")
def test_inspection_probes_exit_without_creating_an_archive(tmp_path: Path) -> None:
    """UC-BSI1: inspection probes never enter the destructive backup flow."""
    root = tmp_path / "root"
    (root / "upstream").mkdir(parents=True)

    help_probe = _run_probe(root, tmp_path, "--help")
    unknown_argument_probe = _run_probe(root, tmp_path, "--definitely-not-a-flag")

    assert help_probe.returncode == 0
    assert help_probe.stdout
    assert unknown_argument_probe.returncode != 0
    assert not (tmp_path / "itsup.tar.gz").exists()
