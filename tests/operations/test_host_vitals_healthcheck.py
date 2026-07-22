import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO_ROOT / "bin" / "pi-healthcheck.sh"
SPEC_ID = "project/spec/feature/operations/host-vitals-healthcheck"


def _write_executable(path: Path, body: str) -> None:
    path.write_text(body)
    path.chmod(0o755)


def _write_healthcheck_fakes(fake_bin: Path, markers: Path) -> None:
    fake_bin.mkdir()
    markers.mkdir()
    _write_executable(
        fake_bin / "awk",
        """#!/usr/bin/env bash
set -euo pipefail
if [[ "$*" == *MemAvailable* ]]; then
  echo 400000
  exit 0
elif [[ "$*" == *loadavg* ]]; then
  echo 1.0
  exit 0
elif [[ "$*" == *BEGIN* ]]; then
  exit 1
fi
exit 1
""",
    )
    _write_executable(
        fake_bin / "cat",
        """#!/usr/bin/env bash
set -euo pipefail
if [[ "$1" == *nf_conntrack_count ]]; then
  echo 1
else
  echo 100
fi
""",
    )
    _write_executable(
        fake_bin / "df",
        """#!/usr/bin/env bash
set -euo pipefail
printf 'Filesystem Use%%\\n/dev/root 1%%\\n'
""",
    )
    _write_executable(
        fake_bin / "date",
        """#!/usr/bin/env bash
set -euo pipefail
if [[ "$1" == "-Is" ]]; then
  echo 2026-07-22T03:00:00+00:00
else
  echo 0300
fi
""",
    )
    _write_executable(
        fake_bin / "docker",
        """#!/usr/bin/env bash
set -euo pipefail
exit 1
""",
    )
    _write_executable(
        fake_bin / "systemctl",
        f"""#!/usr/bin/env bash
set -euo pipefail
touch "{markers}/systemctl-$1"
""",
    )


def _run_healthcheck(root: Path, fake_bin: Path, runtime_directory: Path) -> subprocess.CompletedProcess[str]:
    environment = dict(os.environ)
    environment["PATH"] = f"{fake_bin}:{environment['PATH']}"
    environment["RUNTIME_DIRECTORY"] = str(runtime_directory)
    return subprocess.run(
        [str(root / "bin" / "pi-healthcheck.sh")],
        cwd=root,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


@pytest.mark.functional
@pytest.mark.spec(SPEC_ID, "UC-HVH1")
def test_second_maintenance_window_run_reads_strike_state_and_escalates(tmp_path: Path) -> None:
    """UC-HVH1: a persisted first strike lets the next run reach its escalation."""
    root = tmp_path / "root"
    script_link = root / "bin" / "pi-healthcheck.sh"
    script_link.parent.mkdir(parents=True)
    script_link.symlink_to(SCRIPT)
    markers = tmp_path / "markers"
    fake_bin = tmp_path / "fake-bin"
    _write_healthcheck_fakes(fake_bin, markers)
    itsup = root / ".venv" / "bin" / "itsup"
    itsup.parent.mkdir(parents=True)
    _write_executable(
        itsup,
        f"""#!/usr/bin/env bash
set -euo pipefail
touch {markers / "itsup-ran"}
""",
    )
    runtime_directory = tmp_path / "runtime"
    runtime_directory.mkdir()
    stamp = runtime_directory / "pi-healthcheck.fail"

    first_run = _run_healthcheck(root, fake_bin, runtime_directory)

    assert first_run.returncode == 0, first_run.stderr
    assert stamp.exists()
    assert (markers / "itsup-ran").exists()
    assert (markers / "systemctl-restart").exists()

    second_run = _run_healthcheck(root, fake_bin, runtime_directory)

    assert second_run.returncode == 0, second_run.stderr
    assert not stamp.exists()
    assert (markers / "systemctl-reboot").exists()
