"""Shared fixture-tree helpers for the Traefik artifact-generation deployment tests.

Both test_crowdsec_enforcement.py and test_http_security_middlewares.py build a
temporary itsUP project tree and invoke the real write_traefik_config /
write_middleware_config generation surfaces against it; these helpers are the
one place that mechanics live.
"""

import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import cast

import yaml

from bin.write_artifacts import write_middleware_config, write_traefik_config

ROUTER_IP = "192.168.1.1"

ConfigMap = Mapping[str, object]

# Real repo root, resolved before any test sets ITSUP_ROOT to a temp tree —
# the template source lives here regardless of where root() resolves at test time.
REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def write_project_tree(itsup_root: Path, *, crowdsec_enabled: bool | None = None) -> None:
    crowdsec_stanza = (
        f"""
crowdsec:
  enabled: {str(crowdsec_enabled).lower()}
  apikey: test-key
"""
        if crowdsec_enabled is not None
        else ""
    )

    projects_dir = itsup_root / "projects"
    projects_dir.mkdir(parents=True, exist_ok=True)
    (projects_dir / "itsup.yml").write_text(f"""
routerIP: {ROUTER_IP}
traefikDomain: traefik.example.com
versions:
  traefik: v3.7.8
  crowdsec: v1.7.8
backup:
  enabled: false
{crowdsec_stanza}""")

    secrets_dir = itsup_root / "secrets"
    secrets_dir.mkdir(parents=True, exist_ok=True)
    (secrets_dir / "itsup.txt").write_text("TRAEFIK_ADMIN=admin:$apr1$xyz")

    src_tpl = REPO_ROOT / "tpl"
    dst_tpl = itsup_root / "tpl"
    shutil.copytree(src_tpl, dst_tpl)


def generate(itsup_root: Path) -> tuple[ConfigMap, ConfigMap]:
    write_traefik_config()
    write_middleware_config()

    traefik_yml = itsup_root / "proxy" / "traefik" / "traefik.yml"
    middlewares_yml = itsup_root / "proxy" / "traefik" / "dynamic" / "middlewares.yml"

    traefik_config = cast(ConfigMap, yaml.safe_load(traefik_yml.read_text()))
    middlewares_config = cast(ConfigMap, yaml.safe_load(middlewares_yml.read_text()))
    return traefik_config, middlewares_config


def entrypoint(traefik_config: ConfigMap, name: str) -> ConfigMap:
    entry_points = cast(ConfigMap, traefik_config["entryPoints"])
    return cast(ConfigMap, entry_points[name])


def entrypoint_middlewares(ep: ConfigMap) -> list[object]:
    http_config = cast(ConfigMap, ep.get("http", {}))
    return cast(list[object], http_config.get("middlewares", []))
