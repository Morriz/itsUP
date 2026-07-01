#!/usr/bin/env python3

"""
Functional tests for 'itsup validate' command.

Tests project configuration validation.
Uses REAL project files and validation logic.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from click.testing import CliRunner

from commands.validate import validate

ALL_PROJECTS_VALID = "All projects valid"
TEST_APP_VALID = "test-app: valid"
ERROR = "error"
SERVICE = "service"
API = "api"
INVALID_APP = "invalid-app"
VALID = "valid"


@pytest.fixture(autouse=True)
def _itsup_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Resolve itsUP's install root to the per-test fixture tree."""
    monkeypatch.setenv("ITSUP_ROOT", str(tmp_path))


def test_validate_all_projects_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test validating all projects when all are valid."""
    # Create projects directory structure
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()

    # Create valid project
    project_dir = projects_dir / "test-app"
    project_dir.mkdir()

    # Valid docker-compose.yml
    compose = project_dir / "docker-compose.yml"
    compose.write_text("""
services:
  web:
    image: nginx:latest
    ports:
      - "8080:80"
""")

    # Valid ingress.yml
    ingress = project_dir / "ingress.yml"
    ingress.write_text("""
enabled: true
ingress:
  - service: web
    domain: test.example.com
    port: 80
    router: http
""")

    monkeypatch.chdir(tmp_path)

    runner = CliRunner()
    result = runner.invoke(validate, [])

    assert result.exit_code == 0
    assert ALL_PROJECTS_VALID in result.output


def test_validate_single_project_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test validating a single valid project."""
    # Create projects directory structure
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()

    # Create valid project
    project_dir = projects_dir / "test-app"
    project_dir.mkdir()

    compose = project_dir / "docker-compose.yml"
    compose.write_text("""
services:
  api:
    image: node:18
""")

    ingress = project_dir / "ingress.yml"
    ingress.write_text("""
enabled: true
ingress:
  - service: api
    domain: api.example.com
    port: 3000
    router: http
""")

    monkeypatch.chdir(tmp_path)

    runner = CliRunner()
    result = runner.invoke(validate, ["test-app"])

    assert result.exit_code == 0
    assert TEST_APP_VALID in result.output


def test_validate_project_with_unknown_service(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test validation fails when ingress references non-existent service."""
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()

    project_dir = projects_dir / "bad-app"
    project_dir.mkdir()

    # Compose defines 'web' service
    compose = project_dir / "docker-compose.yml"
    compose.write_text("""
services:
  web:
    image: nginx:latest
""")

    # Ingress references 'api' which doesn't exist
    ingress = project_dir / "ingress.yml"
    ingress.write_text("""
enabled: true
ingress:
  - service: api
    domain: bad.example.com
    port: 3000
    router: http
""")

    monkeypatch.chdir(tmp_path)

    runner = CliRunner()
    result = runner.invoke(validate, ["bad-app"])

    assert result.exit_code == 1
    assert ERROR in result.output.lower()
    assert API in result.output or SERVICE in result.output.lower()


def test_validate_project_missing_compose(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test validation handles missing docker-compose.yml."""
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()

    project_dir = projects_dir / "no-compose"
    project_dir.mkdir()

    # Only ingress, no compose
    ingress = project_dir / "ingress.yml"
    ingress.write_text("""
enabled: true
ingress:
  - service: web
    domain: test.example.com
    port: 80
    router: http
""")

    monkeypatch.chdir(tmp_path)

    runner = CliRunner()
    result = runner.invoke(validate, ["no-compose"])

    assert result.exit_code == 1
    assert ERROR in result.output.lower()


def test_validate_all_with_some_failures(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test validating all projects when some have errors."""
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()

    # Valid project
    valid_dir = projects_dir / "valid-app"
    valid_dir.mkdir()
    (valid_dir / "docker-compose.yml").write_text("""
services:
  web:
    image: nginx:latest
""")
    (valid_dir / "ingress.yml").write_text("""
enabled: true
ingress:
  - service: web
    domain: valid.example.com
    port: 80
    router: http
""")

    # Invalid project (service mismatch)
    invalid_dir = projects_dir / "invalid-app"
    invalid_dir.mkdir()
    (invalid_dir / "docker-compose.yml").write_text("""
services:
  api:
    image: node:18
""")
    (invalid_dir / "ingress.yml").write_text("""
enabled: true
ingress:
  - service: web
    domain: invalid.example.com
    port: 80
    router: http
""")

    monkeypatch.chdir(tmp_path)

    runner = CliRunner()
    result = runner.invoke(validate, [])

    assert result.exit_code == 1
    assert ERROR in result.output.lower()
    assert INVALID_APP in result.output


def test_validate_empty_projects_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test validation when projects/ directory is empty."""
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()

    monkeypatch.chdir(tmp_path)

    runner = CliRunner()
    result = runner.invoke(validate, [])

    assert result.exit_code == 0
    assert VALID in result.output.lower()
