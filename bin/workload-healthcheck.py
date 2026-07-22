from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.data import list_projects, load_project


@dataclass
class Failure:
    project: str
    service: str
    reason: str


def _docker_ids(project: str, service: str) -> list[str]:
    cmd = [
        "docker",
        "ps",
        "--filter",
        f"label=com.docker.compose.project={project}",
        "--filter",
        f"label=com.docker.compose.service={service}",
        "--format",
        "{{.ID}}",
    ]
    result = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "docker ps failed")
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _inspect(container_id: str) -> dict:
    result = subprocess.run(
        ["docker", "inspect", container_id],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"docker inspect failed for {container_id}")
    data = json.loads(result.stdout)
    return data[0] if data else {}


def _status_ok(state: dict, requires_health: bool) -> tuple[bool, str | None]:
    status = state.get("Status")
    if status != "running":
        return False, f"state={status}"

    if requires_health:
        health = state.get("Health", {})
        health_status = health.get("Status")
        if health_status != "healthy":
            return False, f"health={health_status}"

    return True, None


def _has_healthcheck(service: dict) -> bool:
    return isinstance(service, dict) and "healthcheck" in service


def _collect_failures() -> tuple[list[Failure], list[str]]:
    failures: list[Failure] = []
    errors: list[str] = []

    for project in list_projects():
        try:
            compose, traefik = load_project(project)
        except Exception as exc:  # pylint: disable=broad-except
            errors.append(f"project={project} load_error={exc}")
            continue

        if not traefik.enabled:
            continue

        services = compose.get("services", {}) if compose else {}
        if not services:
            # host-only project (no containers)
            continue

        for service_name, service in services.items():
            try:
                ids = _docker_ids(project, service_name)
            except Exception as exc:  # pylint: disable=broad-except
                failures.append(Failure(project, service_name, f"docker_error:{exc}"))
                continue

            if not ids:
                failures.append(Failure(project, service_name, "no_container"))
                continue

            requires_health = _has_healthcheck(service)
            for container_id in ids:
                try:
                    info = _inspect(container_id)
                except Exception as exc:  # pylint: disable=broad-except
                    failures.append(Failure(project, service_name, f"inspect_error:{exc}"))
                    continue

                state = info.get("State", {})
                ok, reason = _status_ok(state, requires_health)
                if not ok and reason:
                    failures.append(Failure(project, service_name, reason))

    return failures, errors


def _print_results(failures: Iterable[Failure], errors: Iterable[str]) -> int:
    failures_list = list(failures)
    errors_list = list(errors)

    for error in errors_list:
        print(f"ERROR {error}")

    for failure in failures_list:
        print(f"FAIL project={failure.project} service={failure.service} reason={failure.reason}")

    print(f"SUMMARY failed={len(failures_list)} errors={len(errors_list)}")
    if errors_list:
        return 2
    return 1 if failures_list else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Check itsUP workload container health")
    parser.add_argument("--quiet", action="store_true", help="Only print summary")
    parser.add_argument(
        "--names-only",
        action="store_true",
        help="Print unique project names only (one per line)",
    )
    args = parser.parse_args()

    failures, errors = _collect_failures()
    if args.names_only:
        projects = sorted({failure.project for failure in failures})
        for project in projects:
            print(project)
        if errors:
            return 2
        return 1 if projects else 0
    if args.quiet:
        print(f"SUMMARY failed={len(failures)} errors={len(errors)}")
        return 2 if errors else (1 if failures else 0)

    return _print_results(failures, errors)


if __name__ == "__main__":
    raise SystemExit(main())
