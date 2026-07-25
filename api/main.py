#!/usr/bin/env python3
import os
import platform
import shutil
import subprocess
import sys
from functools import cache
from typing import List
from urllib.parse import urlparse

import dotenv
import uvicorn
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from instrukt_ai_logging import get_logger

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from lib import supervisor
from lib.alerting import DRIFT_UNITS_CSV_SEPARATOR, DRIFT_UNITS_FLAG
from lib.auth import verify_apikey
from lib.data import list_projects
from lib.deploy import deploy_dns_stack, deploy_proxy_stack
from lib.log_setup import configure_daemon_logging
from lib.paths import root
from lib.reconcile import reconcile
from lib.supervisor import Unit

dotenv.load_dotenv()

app = FastAPI(title="itsUP API", version="2.0")
logger = get_logger(f"itsup.{__name__}")

LINUX_PLATFORM = "Linux"
CHECK_DRIFT_FLAG = "--check-drift"
INSTALL_BRINGUP_SCRIPT_RELATIVE_PATH = "bin/install-bringup.sh"
ALERT_SCRIPT_RELATIVE_PATH = "bin/alert.py"
VENV_PYTHON_RELATIVE_PATH = ".venv/bin/python"
UNIT_DRIFT_DISPLAY_SEPARATOR = ", "

UNIT_DRIFT_LINUX_ONLY_LOG = "Unit-drift check is Linux-only; skipping on %s"
UNIT_DRIFT_CHECK_FAILED_LOG = "Unit-drift check failed: %s"
UNIT_DRIFT_DETECTED_LOG = (
    "Unit-template drift detected (%s); run `make install-runtime` to install the delivered templates"
)
UNIT_DRIFT_CHECK_RAISED_LOG = "Unit-drift check raised: %s"


@cache
def _uv_bin() -> str:
    """Resolve uv's absolute path once. This process runs under systemd/launchd
    supervision with a minimal PATH that may omit ~/.local/bin — the default
    install location of the standalone Astral installer — so a bare "uv" name
    is not reliable here, unlike every other subprocess call in this module."""
    uv_path = shutil.which("uv")
    if uv_path is None:
        raise RuntimeError("uv not found on PATH; required to sync dependencies during self-update")
    return uv_path


def _handle_update_upstream(project: str, service: str = None) -> None:
    """Handle incoming requests to update the upstream - delegates to itsup apply command"""
    try:
        logger.info(f"Updating {project} via webhook...")
        # Use the CLI command which has all the logic. Pass ITSUP_ROOT so the
        # child itsup resolves the same install root regardless of the API's env.
        env = {**os.environ, "ITSUP_ROOT": str(root())}
        subprocess.run([str(root() / ".venv" / "bin" / "itsup"), "apply", project], check=True, env=env)
        logger.info(f"✓ {project} updated successfully")
    except subprocess.CalledProcessError as e:
        logger.info(f"✗ Failed to update {project}: {e}")
        raise


def _check_and_alert_unit_drift(env: dict[str, str]) -> None:
    """Detect systemd-unit drift from the delivered templates and surface it.

    Read-only: `bin/install-bringup.sh --check-drift` never mutates the host.
    Linux-only, and never lets a failure here abort the self-update — a
    checker error or an unexpected exception is logged and swallowed.
    """
    if platform.system() != LINUX_PLATFORM:
        logger.info(UNIT_DRIFT_LINUX_ONLY_LOG, platform.system())
        return

    try:
        result = subprocess.run(
            [str(root() / INSTALL_BRINGUP_SCRIPT_RELATIVE_PATH), CHECK_DRIFT_FLAG],
            cwd=str(root()),
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            logger.warning(UNIT_DRIFT_CHECK_FAILED_LOG, result.stderr.strip())
            return

        units = [line for line in result.stdout.splitlines() if line.strip()]
        if not units:
            return

        logger.warning(UNIT_DRIFT_DETECTED_LOG, UNIT_DRIFT_DISPLAY_SEPARATOR.join(units))
        subprocess.run(
            [
                str(root() / VENV_PYTHON_RELATIVE_PATH),
                str(root() / ALERT_SCRIPT_RELATIVE_PATH),
                DRIFT_UNITS_FLAG,
                DRIFT_UNITS_CSV_SEPARATOR.join(units),
            ],
            cwd=str(root()),
            env=env,
            check=False,
        )
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.warning(UNIT_DRIFT_CHECK_RAISED_LOG, e)


def _handle_itsup_update() -> None:
    """Handle updates to itsUP itself (git pull and apply changes)"""
    try:
        # ITSUP_ROOT for every child runtime process,
        # so root() resolves the same install root regardless of the API's env.
        env = {**os.environ, "ITSUP_ROOT": str(root())}

        # Update repository
        if os.environ.get("PYTHON_ENV") == "production":
            logger.info("Updating repository from origin/main")
            subprocess.run(["git", "fetch", "origin", "main"], cwd=str(root()), check=True)
            subprocess.run(["git", "reset", "--hard", "origin/main"], cwd=str(root()), check=True)
            logger.info("Repository updated successfully")

            # git reset bypasses the post-merge hook that syncs dependencies,
            # so sync explicitly — a dependency-adding update otherwise leaves
            # the API importing a missing module on restart.
            logger.info("Installing dependencies")
            # uv sync --no-dev re-mints the .venv/bin/itsup console-script (entry
            # point / package layout changes included) and installs runtime-only
            # deps from uv.lock, pruning the venv to exactly that set.
            subprocess.run(
                [_uv_bin(), "sync", "--no-dev"],
                cwd=str(root()),
                check=True,
            )

            _check_and_alert_unit_drift(env)

        # Deploy infrastructure stacks with smart rollout
        logger.info("Deploying DNS stack...")
        deploy_dns_stack()

        logger.info("Deploying proxy stack (regenerates artifacts + zero-downtime rollout)...")
        deploy_proxy_stack()

        # Apply all upstream project changes
        logger.info("Deploying all upstream projects...")
        subprocess.run([str(root() / ".venv" / "bin" / "itsup"), "apply"], check=True, env=env)

        # Restart API to pick up new code
        logger.info("Restarting API server")
        supervisor.restart(Unit.API)

    except Exception as e:
        logger.info(f"✗ Failed to update itsUP: {e}")
        raise


def _handle_hook(project: str, background_tasks: BackgroundTasks, service: str = None) -> None:
    """Handle incoming webhook requests to update projects"""
    if project == "itsUP":
        background_tasks.add_task(_handle_itsup_update)
        return

    # Validate project exists
    projects = list_projects()
    if project not in projects:
        logger.info(f"Project {project} not found. Available: {', '.join(projects)}")
        return

    background_tasks.add_task(_handle_update_upstream, project=project, service=service)


@app.get("/update-upstream/{project}", response_model=None)
@app.get("/update-upstream/{project}/{service}", response_model=None)
def get_hook_handler(
    project: str,
    background_tasks: BackgroundTasks,
    service: str = None,
    _: None = Depends(verify_apikey),
) -> None:
    """Handle requests to update the upstream"""
    _handle_hook(project, background_tasks, service)


@app.post("/reconcile", response_model=None)
def reconcile_handler(
    background_tasks: BackgroundTasks,
    _: None = Depends(verify_apikey),
) -> None:
    """Reconcile the full stack from the projects/secrets config repos.

    Triggered by a webhook when either config repo receives a commit: pulls both
    repos then runs `itsup apply`. Convergent and single-flight — overlapping
    triggers coalesce into one trailing run.
    """
    background_tasks.add_task(reconcile)


@app.get("/projects", response_model=List[str])
@cache
def list_projects_handler(_: None = Depends(verify_apikey)) -> List[str]:
    """Get the list of all projects (V2 - file-based configuration)"""
    return list_projects()


@app.get("/redirect", response_class=RedirectResponse)
def redirect_handler(url: str) -> RedirectResponse:
    """Redirect to the provided url (message:// or imessage:// only)."""
    if not url:
        raise HTTPException(status_code=400, detail="Missing url")

    parsed = urlparse(url)
    if parsed.scheme not in {"message", "imessage"}:
        raise HTTPException(status_code=400, detail="Unsupported url scheme")

    if any(char.isspace() for char in url):
        raise HTTPException(status_code=400, detail="Invalid url")

    return RedirectResponse(url=url, status_code=307)


if __name__ == "__main__":
    configure_daemon_logging()
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8888,
        reload_dirs=["."],
        forwarded_allow_ips="*",
        proxy_headers=os.environ.get("PYTHON_ENV", "development") == "production",
    )
