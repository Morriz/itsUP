#!/usr/bin/env python3
from __future__ import annotations


# Re-exec under the project venv so direct invocation works from any interpreter.
import os as _os
import sys as _sys

_VENV = _os.path.normpath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", ".venv"))
_VENV_PYTHON = _os.path.join(_VENV, "bin", "python")
if (
    __name__ == "__main__"
    and _os.path.exists(_VENV_PYTHON)
    and _os.path.realpath(_sys.prefix) != _os.path.realpath(_VENV)
):
    _os.execv(_VENV_PYTHON, [_VENV_PYTHON, _os.path.abspath(__file__), *_sys.argv[1:]])

import argparse
import re
import ssl
import sys
from dataclasses import dataclass
from http.client import HTTPSConnection
from pathlib import Path
from typing import Iterable
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.data import list_projects, load_project
from lib.models import Ingress, Router


URL_RE = re.compile(r"https?://[^\s'\"\\]+")


@dataclass
class Check:
    project: str
    service: str | None
    domain: str
    path: str
    source: str
    router: str
    port: int
    passthrough: bool


@dataclass
class Skip:
    project: str
    service: str | None
    domain: str | None
    reason: str


@dataclass
class Result:
    check: Check
    ok: bool
    status: int | None
    error: str | None


def _extract_healthcheck_urls(service: dict) -> list[tuple[int | None, str]]:
    healthcheck = service.get("healthcheck") if service else None
    if not isinstance(healthcheck, dict):
        return []

    test = healthcheck.get("test")
    if not test:
        return []

    if isinstance(test, list):
        combined = " ".join(str(part) for part in test)
    else:
        combined = str(test)

    urls = []
    for match in URL_RE.findall(combined):
        parsed = urlsplit(match)
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"
        urls.append((parsed.port, path))
    return urls


def _infer_path(ingress: Ingress, compose: dict) -> tuple[str, str]:
    if ingress.service and compose:
        services = compose.get("services", {})
        service = services.get(ingress.service)
        for port, path in _extract_healthcheck_urls(service):
            if port is None:
                if ingress.port in (80, 443):
                    return path, "healthcheck"
                continue
            if port == ingress.port:
                return path, "healthcheck"

    if ingress.path_prefix:
        path_prefix = ingress.path_prefix
        if not path_prefix.startswith("/"):
            path_prefix = f"/{path_prefix}"
        return path_prefix, "path_prefix"

    return "/", "root"


def _https_eligible(ingress: Ingress) -> tuple[bool, str]:
    if ingress.router == Router.http:
        return True, "router=http"
    if ingress.router == Router.tcp:
        if ingress.passthrough or ingress.tls is not None or ingress.port == 443:
            return True, "router=tcp tls/passthrough/443"
        return False, "router=tcp without tls"
    return False, "router=udp"


def _domains_for_ingress(ingress: Ingress) -> list[str]:
    domains: list[str] = []
    if ingress.domain:
        domains.append(ingress.domain)
    if ingress.tls:
        if ingress.tls.main:
            domains.append(ingress.tls.main)
        domains.extend(ingress.tls.sans)
    seen = set()
    ordered = []
    for domain in domains:
        if domain in seen:
            continue
        seen.add(domain)
        ordered.append(domain)
    return ordered


def _build_checks() -> tuple[list[Check], list[Skip]]:
    checks: list[Check] = []
    skips: list[Skip] = []

    for project in list_projects():
        compose, traefik = load_project(project)
        if not traefik.enabled:
            skips.append(Skip(project, None, None, "project disabled"))
            continue

        for ingress in traefik.ingress:
            if ingress is None:
                continue
            domains = _domains_for_ingress(ingress)
            if not domains:
                skips.append(Skip(project, ingress.service, None, "no domain/tls specified"))
                continue

            https_ok, reason = _https_eligible(ingress)
            if not https_ok:
                for domain in domains:
                    skips.append(Skip(project, ingress.service, domain, reason))
                continue

            path, source = _infer_path(ingress, compose)
            for domain in domains:
                checks.append(
                    Check(
                        project=project,
                        service=ingress.service,
                        domain=domain,
                        path=path,
                        source=source,
                        router=ingress.router.value,
                        port=ingress.port,
                        passthrough=ingress.passthrough,
                    )
                )

    return checks, skips


def _https_get(domain: str, path: str, timeout: float) -> tuple[int | None, str | None]:
    context = ssl.create_default_context()
    conn = HTTPSConnection(domain, timeout=timeout, context=context)
    try:
        conn.request(
            "GET",
            path,
            headers={
                "User-Agent": "itsup-endpoint-check/1.0",
                "Accept": "*/*",
            },
        )
        resp = conn.getresponse()
        status = resp.status
        resp.read(256)
        return status, None
    except Exception as exc:  # pylint: disable=broad-except
        return None, str(exc)
    finally:
        conn.close()


def _status_ok(status: int | None) -> bool:
    if status is None:
        return False
    return 200 <= status < 400


def _print_results(results: Iterable[Result], skips: list[Skip]) -> int:
    failures = 0
    total = 0
    for result in results:
        total += 1
        url = f"https://{result.check.domain}{result.check.path}"
        if result.ok:
            print(
                f"OK {url} status={result.status} project={result.check.project} service={result.check.service} source={result.check.source}"
            )
        else:
            failures += 1
            detail = result.error or f"status={result.status}"
            print(
                f"FAIL {url} {detail} project={result.check.project} service={result.check.service} source={result.check.source}"
            )

    for skip in skips:
        domain = skip.domain or "-"
        service = skip.service or "-"
        print(f"SKIP {domain} project={skip.project} service={service} reason={skip.reason}")

    print(f"SUMMARY total={total} failed={failures} skipped={len(skips)}")
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="HTTPS endpoint checks from itsUP project ingress")
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args()

    checks, skips = _build_checks()
    results: list[Result] = []
    for check in checks:
        status, error = _https_get(check.domain, check.path, args.timeout)
        ok = _status_ok(status)
        results.append(Result(check=check, ok=ok, status=status, error=error))

    return _print_results(results, skips)


if __name__ == "__main__":
    raise SystemExit(main())
