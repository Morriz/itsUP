#!/usr/bin/env python3

"""Regression coverage for UC-CV1 and UC-CV2 of the config-validation spec.

Two independent boundaries, both against a scratch install root:

- UC-CV1 (Compose-schema rejection): the real CLI (``itsup.cli`` ``validate``
  command), invoked in-process via click's ``CliRunner`` — the same
  real-boundary shape as ``tests/functional/test_cli_cwd_independence.py``.
  The real ``docker compose`` binary is exercised for real; these cases skip
  when it is unavailable, following the precedent in
  ``tests/functional/bin/test_write_artifacts.py``.
- UC-CV2 (unresolved-placeholder rejection): real proxy-artifact generation
  (``bin.write_artifacts.write_proxy_artifacts``), the same entry point
  ``commands/run.py`` and ``lib/deploy.py`` call before every deploy. This
  boundary invokes no Docker at all, so it runs unconditionally.
"""

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner
from syrupy.assertion import SnapshotAssertion

from bin.write_artifacts import write_proxy_artifacts
from itsup.cli import cli
from lib.data import COMPOSE_SCHEMA_FAILURE_PREFIX

SPEC_ID = "project/spec/feature/deployment/config-validation"

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


@pytest.fixture
def _skip_without_docker() -> None:
    """Skip a Compose-schema case when the docker CLI is unavailable (e.g. minimal CI)."""
    try:
        subprocess.run(["docker", "compose", "version"], capture_output=True, timeout=10, check=False)
    except FileNotFoundError:
        pytest.skip("Docker not available - skipping compose schema validation")


@pytest.fixture(name="scratch_root")
def scratch_root_fixture(tmp_path: Path) -> Path:
    """A complete install tree: pyproject + schema-matched itsup.yml + secrets/.

    Mirrors ``install_root_fixture`` in ``test_cli_cwd_independence.py`` — the
    real CLI's ``guard_schema_version`` reads both files, so they must satisfy
    the real schema-version check.
    """
    (tmp_path / "pyproject.toml").write_text('[project]\nversion = "2.1.1"\n')
    projects = tmp_path / "projects"
    projects.mkdir()
    (projects / "itsup.yml").write_text('schemaVersion: "2.1.0"\nrouterIP: 192.168.1.1\n')
    (tmp_path / "secrets").mkdir()
    return tmp_path


def _write_project(scratch_root: Path, name: str, compose_yaml: str) -> None:
    project = scratch_root / "projects" / name
    project.mkdir(parents=True)
    (project / "docker-compose.yml").write_text(compose_yaml)
    (project / "itsup-project.yml").write_text("enabled: true\n")


def _validate(scratch_root: Path, project: str) -> tuple[int, str]:
    """Run the real CLI's validate command in-process, return combined output."""
    runner = CliRunner()
    result = runner.invoke(cli, ["validate", project], env={"ITSUP_ROOT": str(scratch_root)})
    return result.exit_code, result.output


@pytest.mark.functional
@pytest.mark.spec(SPEC_ID, "UC-CV1")
def test_reported_healthcheck_shape_is_rejected(scratch_root: Path, _skip_without_docker: None) -> None:
    """UC-CV1: the exact reported healthcheck.test shape is YAML-valid but Compose-invalid."""
    _write_project(
        scratch_root,
        "repro",
        "services:\n"
        "  repro-frontend:\n"
        "    image: nginx:alpine\n"
        "    healthcheck:\n"
        "      test:\n"
        "        - CMD-SHELL\n"
        '        - curl -fsS -H "Host: $$HEALTHCHECK_SITE" http://localhost:8080/api/method/ping || exit 1\n',
    )

    exit_code, output = _validate(scratch_root, "repro")

    assert exit_code != 0
    assert COMPOSE_SCHEMA_FAILURE_PREFIX in output


@pytest.mark.functional
@pytest.mark.spec(SPEC_ID, "UC-CV1")
def test_falsy_compose_document_is_still_schema_checked(scratch_root: Path, _skip_without_docker: None) -> None:
    """UC-CV1: a present but comments-only docker-compose.yml is rejected, not skipped."""
    _write_project(scratch_root, "empty-compose", "# just a comment\n")

    exit_code, output = _validate(scratch_root, "empty-compose")

    assert exit_code != 0
    assert COMPOSE_SCHEMA_FAILURE_PREFIX in output


@pytest.mark.functional
@pytest.mark.spec(SPEC_ID, "UC-CV1")
def test_required_variable_without_secret_still_passes(
    scratch_root: Path, monkeypatch: pytest.MonkeyPatch, _skip_without_docker: None
) -> None:
    """UC-CV1 acceptance contrast: a Compose-valid file with an unset required
    variable and no decryptable secret still passes — the schema verdict is
    interpolation-independent, so valid secret-backed files pass on keyless
    runs-anywhere machines."""
    # bin/write_artifacts.py calls load_dotenv() at import, which can pull
    # API_KEY in from a real .env found by walking up from this worktree;
    # scrub it so the Given ("API_KEY absent") holds regardless of ambient env.
    monkeypatch.delenv("API_KEY", raising=False)
    _write_project(
        scratch_root,
        "needs-secret",
        "services:\n"
        "  web:\n"
        "    image: nginx:alpine\n"
        "    environment:\n"
        "      API_KEY: ${API_KEY:?required}\n",
    )

    exit_code, output = _validate(scratch_root, "needs-secret")

    assert exit_code == 0
    assert COMPOSE_SCHEMA_FAILURE_PREFIX not in output


@pytest.fixture(name="generation_root")
def generation_root_fixture(scratch_root: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """``scratch_root`` extended with everything real proxy-artifact generation needs.

    Mirrors the proven shape in ``tests/deployment/conftest.py:write_project_tree``:
    the ``tpl/`` templates every writer reads from ``root()``, the config keys
    ``write_dynamic_routers`` and the proxy compose template require
    (``traefikDomain``, ``versions.traefik``, ``versions.crowdsec``,
    ``crowdsec.enabled``), and the secrets ``write_middleware_config`` /
    ``write_traefik_config`` require (``TRAEFIK_ADMIN``, ``LETSENCRYPT_EMAIL``).
    Layered on this module's own ``scratch_root`` fixture so the module keeps
    one owning fixture tree for both UC-CV1 and UC-CV2 cases.
    """
    monkeypatch.setenv("ITSUP_ROOT", str(scratch_root))

    (scratch_root / "projects" / "itsup.yml").write_text("""
schemaVersion: "2.1.0"
routerIP: 192.168.1.1
traefikDomain: traefik.example.com
versions:
  traefik: v3.7.8
  crowdsec: v1.7.8
crowdsec:
  enabled: false
backup:
  enabled: false
""")
    (scratch_root / "secrets" / "itsup.txt").write_text(
        "TRAEFIK_ADMIN=admin:$apr1$xyz\nLETSENCRYPT_EMAIL=admin@example.com\n"
    )
    shutil.copytree(REPO_ROOT / "tpl", scratch_root / "tpl")

    return scratch_root


@pytest.mark.functional
@pytest.mark.spec(SPEC_ID, "UC-CV2")
def test_unresolved_placeholder_is_rejected(generation_root: Path, snapshot: SnapshotAssertion) -> None:
    """UC-CV2: an unresolved ${VAR} in a middlewares.yml override fails generation
    at the placeholder, and the dynamic middleware artifact it belongs to is
    withheld — not written with the residue in it."""
    (generation_root / "projects" / "middlewares.yml").write_text("""
http:
  middlewares:
    custom:
      basicAuth:
        users:
          - ${SOME_UNSET_VAR}
""")

    middlewares_file = generation_root / "proxy" / "traefik" / "dynamic" / "middlewares.yml"

    with pytest.raises(ValueError) as exc_info:
        write_proxy_artifacts()

    assert not middlewares_file.exists()
    assert str(exc_info.value).replace(str(generation_root), "<ROOT>") == snapshot


@pytest.mark.functional
@pytest.mark.spec(SPEC_ID, "UC-CV2")
def test_clean_generation_preserves_compose_placeholders(generation_root: Path, snapshot: SnapshotAssertion) -> None:
    """UC-CV2 acceptance contrast: a clean tree (no override placeholder) generates
    successfully; the generated Traefik artifacts, read back from disk, carry no
    unresolved placeholder residue, and the generated Compose file's traefik-service
    environment still carries its own required-variable Compose placeholder —
    Compose owns that interpolation contract, not this gate."""
    write_proxy_artifacts()

    traefik_yml = generation_root / "proxy" / "traefik" / "traefik.yml"
    middlewares_yml = generation_root / "proxy" / "traefik" / "dynamic" / "middlewares.yml"
    compose_yml = generation_root / "proxy" / "docker-compose.yml"

    assert traefik_yml.read_text() == snapshot(name="traefik_yml")
    assert middlewares_yml.read_text() == snapshot(name="middlewares_yml")

    compose_config = yaml.safe_load(compose_yml.read_text())
    assert compose_config["services"]["traefik"]["environment"] == snapshot(name="compose_traefik_environment")
