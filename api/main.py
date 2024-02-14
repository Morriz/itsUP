import os
from typing import Any, Dict, List

import dotenv
import uvicorn
from fastapi import BackgroundTasks, Depends
from github_webhooks import create_app

from lib.auth import verify_apikey
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
from lib.models import PingPayload, Project, Service, WorkflowJobPayload
from lib.proxy import reload_proxy, write_nginx
from lib.upstream import check_upstream, update_upstream, write_upstreams

dotenv.load_dotenv()


api_token = os.environ["API_KEY"]
app = create_app(secret_token=api_token)


def _after_config_change(project: str) -> None:
    """Run after a project is updated"""
    write_nginx()
    write_upstreams()
    update_upstream(project)
    reload_proxy()


def _handle_update_upstream(project: str, service: str) -> None:
    """handle incoming requests to update the upstream"""
    check_upstream(project, service)
    update_upstream(project, service, rollout=True)
    # reload proxy's terminate service as it needs to get the new upstream
    reload_proxy("terminate")


@app.get("/update-upstream", response_model=None)
def get_hook_handler(
    project: str,
    background_tasks: BackgroundTasks,
    service: str = None,
    _: None = Depends(verify_apikey),
) -> None:
    """Handle requests to update the upstream"""
    if project == "uptid":
        background_tasks.add_task(update_repo)
        return
    background_tasks.add_task(_handle_update_upstream, project=project, service=service)


@app.hooks.register("ping", PingPayload)
async def github_ping_handler(
    payload: PingPayload,
    **_: Any,
) -> str:
    """Handle incoming github webhook requests for ping events to notify callers we're up"""
    print(f"Got ping message: {payload.zen}")
    return "pong"


@app.hooks.register("workflow_job", WorkflowJobPayload)
async def github_workflow_job_handler(
    payload: WorkflowJobPayload, query_params: Dict[str, str], background_tasks: BackgroundTasks, **_: Any
) -> None:
    """Handle incoming github webhook requests for workflow_job events to update ourselves or an upstream"""
    if payload.workflow_job.status == "completed" and payload.workflow_job.conclusion == "success":
        project = query_params.get("project")
        assert project is not None
        if project == "uptid":
            background_tasks.add_task(update_repo)
            return
        # needs to be set correctly in the project's workflow file:
        service = payload.workflow_job.name
        background_tasks.add_task(_handle_update_upstream, project=project, service=service)


@app.get("/projects/{project}", response_model=List[Service])
def get_projects_handler(project: str = None, _: None = Depends(verify_apikey)) -> List[Project] | Project:
    """Get the list of all or one project"""
    if project:
        return get_project(project, throw=True)
    return get_projects()


@app.get("/projects/{project}/services/{service}", response_model=Service)
def get_project_services_handler(
    project: str, service: str = None, _: None = Depends(verify_apikey)
) -> Service | List[Service]:
    """Get the list of a project's services, or a specific one"""
    if service:
        return get_service(project, service, throw=True)
    p = get_project(project, throw=True)
    return p.services


@app.get("/projects/{project}/services/{service}/env", response_model=Service)
def get_env_handler(project: str, service: str, _: None = Depends(verify_apikey)) -> Dict[str, str]:
    """Get the list of a project's services, or a specific one"""
    return get_env(project, service)


@app.post("/projects", tags=["Project"])
def post_project_handler(
    project: Project,
    _: None = Depends(verify_apikey),
) -> None:
    """Create or update a project"""
    upsert_project(project)
    _after_config_change(project.name)


@app.get("/services", response_model=List[Service])
def get_services_handler(_: None = Depends(verify_apikey)) -> List[Service]:
    """Get the list of all services"""
    return get_services()


@app.post("/services", tags=["Service"])
def post_service_handler(
    project: str,
    service: Service,
    _: None = Depends(verify_apikey),
) -> None:
    """Create or update a service"""
    upsert_service(project, service)
    _after_config_change(project)


@app.post("/projects/{project}/services/{service}/env", tags=["Service"])
def post_env_handler(
    project: str,
    service: str,
    env: Dict[str, str],
    _: None = Depends(verify_apikey),
) -> None:
    """Create or update env for a project service"""
    upsert_env(project, service, env)
    _after_config_change(project)


if __name__ == "__main__":

    uvicorn.run(app, host="0.0.0.0", port=8888, log_level="debug", reload_dirs=["."])
