#!.venv/bin/python
import os
from logging import info
from typing import Any, Dict, List

import dotenv
import uvicorn
from fastapi import BackgroundTasks, Depends
from github_webhooks import create_app

from lib.auth import verify_apikey
from lib.certs import get_certs
from lib.data import (
    get_env,
    get_project,
    get_projects,
    get_service,
    get_services,
    upsert_env,
    upsert_project,
    upsert_service,
)
from lib.git import update_repo
from lib.models import Env, PingPayload, Project, Service, WorkflowJobPayload
from lib.proxy import reload_proxy, update_proxy, write_proxies
from lib.upstream import check_upstream, update_upstream, write_upstreams

dotenv.load_dotenv()


api_token = os.environ["API_KEY"]
app = create_app(secret_token=api_token)


def _after_config_change(project: str, service: str = None) -> None:
    """Run after a project is updated"""
    info("Config change detected")
    get_certs(project)
    write_proxies()
    write_upstreams()
    update_upstream(project, service, rollout=True)
    update_proxy()
    reload_proxy()


def _handle_update_upstream(project: str, service: str) -> None:
    """handle incoming requests to update the upstream"""
    update_upstream(project, service, rollout=True)
    # reload proxy's terminate service as it needs to get the new upstream
    reload_proxy("terminate")


def _handle_hook(project: str, background_tasks: BackgroundTasks, service: str = None) -> None:
    """Handle incoming requests to update the upstream"""
    if project == "itsUP":
        background_tasks.add_task(update_repo)
        return
    check_upstream(project, service)
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


@app.hooks.register("ping", PingPayload)
async def github_ping_handler(
    payload: PingPayload,
    **_: Any,
) -> str:
    """Handle incoming github webhook requests for ping events to notify callers we're up"""
    info(f"Got ping message: {payload.zen}")
    return "pong"


@app.hooks.register("workflow_job", WorkflowJobPayload)
async def github_workflow_job_handler(
    payload: WorkflowJobPayload, query_params: Dict[str, str], background_tasks: BackgroundTasks, **_: Any
) -> None:
    """Handle incoming github webhook requests for workflow_job events to update ourselves or an upstream"""
    if payload.workflow_job.status == "completed" and payload.workflow_job.conclusion == "success":
        project = query_params.get("project")
        assert project is not None
        service = payload.workflow_job.name
        _handle_hook(project, background_tasks, service)


@app.get("/projects", response_model=List[Project])
@app.get("/projects/{project}", response_model=Project)
def get_projects_handler(project: str = None, _: None = Depends(verify_apikey)) -> List[Project] | Project:
    """Get the list of all or one project"""
    if project:
        return get_project(project, throw=True)
    return get_projects()


@app.get("/projects/{project}/services", response_model=List[Service])
@app.get("/projects/{project}/services/{service}", response_model=Service)
def get_project_services_handler(
    project: str, service: str = None, _: None = Depends(verify_apikey)
) -> Service | List[Service]:
    """Get the list of a project's services, or a specific one"""
    if service:
        return get_service(project, service, throw=True)
    return get_project(project, throw=True).services


@app.get("/projects/{project}/services/{service}/env", response_model=Env)
def get_env_handler(project: str, service: str, _: None = Depends(verify_apikey)) -> Dict[str, str]:
    """Get the list of a project's service' env vars"""
    return get_env(project, service)


@app.post("/projects", tags=["Project"])
def post_project_handler(
    project: Project,
    background_tasks: BackgroundTasks,
    _: None = Depends(verify_apikey),
) -> None:
    """Create or update a project"""
    upsert_project(project)
    background_tasks.add_task(_after_config_change, project.name)


@app.get("/services", response_model=List[Service])
def get_services_handler(_: None = Depends(verify_apikey)) -> List[Service]:
    """Get the list of all services"""
    return get_services()


@app.post("/services", tags=["Service"])
def post_service_handler(
    project: str,
    service: Service,
    background_tasks: BackgroundTasks,
    _: None = Depends(verify_apikey),
) -> None:
    """Create or update a service"""
    upsert_service(project, service)
    background_tasks.add_task(_after_config_change, project, service.name)


@app.post(
    "/projects/{project}/services/{service}/env",
    tags=["Env"],
)
def post_env_handler(
    project: str,
    service: str,
    env: Env,
    background_tasks: BackgroundTasks,
    _: None = Depends(verify_apikey),
) -> None:
    """Create or update env for a project service"""
    upsert_env(project, service, env)
    background_tasks.add_task(_after_config_change, project, service)


if __name__ == "__main__":

    uvicorn.run(app, host="0.0.0.0", port=8888, log_level="debug", reload_dirs=["."], log_config="api-log.conf.yaml")
