#!/usr/bin/env python3
import os
import subprocess
import sys
from functools import cache
from logging import info
from typing import List
from urllib.parse import urlparse

import dotenv
import uvicorn
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException
from fastapi.responses import RedirectResponse

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from lib.auth import verify_apikey
from lib.data import list_projects
from lib.deploy import deploy_dns_stack, deploy_proxy_stack

dotenv.load_dotenv()

app = FastAPI(title="itsUP API", version="2.0")


def _handle_update_upstream(project: str, service: str = None) -> None:
    """Handle incoming requests to update the upstream - delegates to itsup apply command"""
    try:
        info(f"Updating {project} via webhook...")
        # Use the CLI command which has all the logic
        subprocess.run(["bin/itsup", "apply", project], check=True)
        info(f"✓ {project} updated successfully")
    except subprocess.CalledProcessError as e:
        info(f"✗ Failed to update {project}: {e}")
        raise


def _handle_itsup_update() -> None:
    """Handle updates to itsUP itself (git pull and apply changes)"""
    try:
        # Update repository
        if os.environ.get("PYTHON_ENV") == "production":
            info("Updating repository from origin/main")
            subprocess.run(["git", "fetch", "origin", "main"], cwd=".", check=True)
            subprocess.run(["git", "reset", "--hard", "origin/main"], cwd=".", check=True)
            info("Repository updated successfully")

        # Deploy infrastructure stacks with smart rollout
        info("Deploying DNS stack...")
        deploy_dns_stack()

        info("Deploying proxy stack (regenerates artifacts + zero-downtime rollout)...")
        deploy_proxy_stack()

        # Apply all upstream project changes
        info("Deploying all upstream projects...")
        subprocess.run(["bin/itsup", "apply"], check=True)

        # Restart API to pick up new code
        info("Restarting API server")
        subprocess.run(["./bin/start-api.sh"], check=True)

    except Exception as e:
        info(f"✗ Failed to update itsUP: {e}")
        raise


def _handle_hook(project: str, background_tasks: BackgroundTasks, service: str = None) -> None:
    """Handle incoming webhook requests to update projects"""
    if project == "itsUP":
        background_tasks.add_task(_handle_itsup_update)
        return

    # Validate project exists
    projects = list_projects()
    if project not in projects:
        info(f"Project {project} not found. Available: {', '.join(projects)}")
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

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8888,
        log_level="debug",
        reload_dirs=["."],
        forwarded_allow_ips="*",
        log_config="api-log.conf.yaml",
        proxy_headers=os.environ.get("PYTHON_ENV", "development") == "production",
    )
