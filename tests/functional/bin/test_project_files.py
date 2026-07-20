from pathlib import Path

import pytest

from bin.write_artifacts import write_upstream


@pytest.mark.functional
def test_project_files_are_mirrored_into_upstream(isolated_itsup_root: Path) -> None:
    """Generated upstream artifacts include only the project's current deployable files."""
    project_dir = isolated_itsup_root / "projects" / "test-project"
    source_files = project_dir / "files"
    source_files.mkdir(parents=True)
    (project_dir / "docker-compose.yml").write_text("services:\n  web:\n    image: nginx:alpine\n")

    source_script = source_files / "bin" / "configure.sh"
    source_script.parent.mkdir()
    source_script.write_text("#!/usr/bin/env bash\n")
    source_script.chmod(0o755)

    stale_file = isolated_itsup_root / "upstream" / "test-project" / "files" / "stale.sh"
    stale_file.parent.mkdir(parents=True)
    stale_file.write_text("stale")

    write_upstream("test-project")

    staged_script = isolated_itsup_root / "upstream" / "test-project" / "files" / "bin" / "configure.sh"
    assert staged_script.read_bytes() == source_script.read_bytes()
    assert staged_script.stat().st_mode & 0o100
    assert not stale_file.exists()
