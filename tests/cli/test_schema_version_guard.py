from pathlib import Path

import pytest
from click.testing import CliRunner

from commands.validate import validate

SPEC_ID = "project/spec/feature/cli/schema-version-guard"


@pytest.mark.functional
@pytest.mark.spec(SPEC_ID, "UC-SVG1")
def test_outdated_schema_blocks_validate_before_project_validation(isolated_itsup_root: Path) -> None:
    """UC-SVG1: An outdated config schema blocks validate before project validation."""
    (isolated_itsup_root / "pyproject.toml").write_text('[project]\nversion = "2.0.0"\n')
    projects = isolated_itsup_root / "projects"
    projects.mkdir()
    (projects / "itsup.yml").write_text("schemaVersion: 1.0.0\n")

    result = CliRunner().invoke(validate)

    assert result.exit_code != 0
    assert result.output
