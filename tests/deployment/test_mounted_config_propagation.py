import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

from bin.write_artifacts import write_proxy_artifacts
from lib.deploy import deploy_proxy_stack
from tests.deployment.conftest import write_project_tree

SPEC_ID = "project/spec/feature/deployment/mounted-config-propagation"
CONFIG_HASH = "current-config-hash"


def _set_crowdsec_enabled(itsup_root: Path) -> None:
    config_path = itsup_root / "projects" / "itsup.yml"
    config_path.write_text(config_path.read_text().replace("enabled: false", "enabled: true"))


def _fake_docker_run(
    rollouts: list[list[str]], traefik_running: bool
) -> Callable[..., subprocess.CompletedProcess[str]]:
    def run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        if command[:2] == ["docker", "ps"]:
            stdout = "proxy-traefik-1\n" if traefik_running else ""
        elif command[:4] == ["docker", "compose", "config", "--hash"]:
            stdout = f"traefik {CONFIG_HASH}\n"
        elif command[:2] == ["docker", "inspect"]:
            stdout = f"{CONFIG_HASH}\n"
        elif command[:2] == ["docker", "rollout"]:
            rollouts.append(command)
            stdout = ""
        else:
            stdout = ""
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    return run


@pytest.mark.functional
@pytest.mark.spec(SPEC_ID, "UC-MCP1")
def test_changed_static_config_rolls_out_running_traefik(
    isolated_itsup_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_project_tree(isolated_itsup_root, crowdsec_enabled=False)
    write_proxy_artifacts()
    _set_crowdsec_enabled(isolated_itsup_root)
    rollouts: list[list[str]] = []
    monkeypatch.setattr("lib.deploy.subprocess.run", _fake_docker_run(rollouts, traefik_running=True))

    deploy_proxy_stack()

    assert rollouts == [["docker", "rollout", "traefik"]]


@pytest.mark.functional
@pytest.mark.spec(SPEC_ID, "UC-MCP1")
def test_unchanged_static_config_does_not_roll_out_traefik(
    isolated_itsup_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_project_tree(isolated_itsup_root, crowdsec_enabled=False)
    write_proxy_artifacts()
    rollouts: list[list[str]] = []
    monkeypatch.setattr("lib.deploy.subprocess.run", _fake_docker_run(rollouts, traefik_running=True))

    deploy_proxy_stack()

    assert not rollouts


@pytest.mark.functional
@pytest.mark.spec(SPEC_ID, "UC-MCP1")
def test_changed_static_config_on_first_deploy_does_not_roll_out_traefik(
    isolated_itsup_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_project_tree(isolated_itsup_root, crowdsec_enabled=False)
    write_proxy_artifacts()
    _set_crowdsec_enabled(isolated_itsup_root)
    rollouts: list[list[str]] = []
    monkeypatch.setattr("lib.deploy.subprocess.run", _fake_docker_run(rollouts, traefik_running=False))

    deploy_proxy_stack()

    assert not rollouts
