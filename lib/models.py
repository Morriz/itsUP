from typing import Dict, List

from github_webhooks.schemas import WebhookCommonPayload
from pydantic import BaseModel

# pylint: disable=too-few-public-methods


class Service(BaseModel):
    """Service model"""

    svc: str
    port: int
    project: str = None
    domain: str = None
    image: str = None
    command: str = None
    passthrough: bool = False
    upstream: bool = False
    volumes: List[str] = []
    env: Dict[str, str] = {}


class Project(BaseModel):
    """Project model"""

    name: str
    description: str = None
    domain: str = None
    upstream: str = None
    services: List[Service] = []


class PingPayload(WebhookCommonPayload):

    zen: str


class WorkflowJobPayload(WebhookCommonPayload):
    class WorkflowJob(BaseModel):
        name: str
        status: str
        conclusion: str

    workflow_job: WorkflowJob
