from typing import Any, Dict, List

from github_webhooks.schemas import WebhookCommonPayload
from pydantic import BaseModel, ConfigDict


class Env(BaseModel):
    model_config = ConfigDict(extra="allow")


class Service(BaseModel):
    """Service model"""

    name: str
    port: int = 8080
    """When set, the service will be exposed on this domain."""
    image: str = None
    command: str = None
    passthrough: bool = False
    """Wether or not traffic to this service is forwarded as-is (without terminating SSL)"""
    volumes: List[str] = []
    env: Env = None
    """A dictionary of environment variables to pass to the service"""


class Project(BaseModel):
    """Project model"""

    name: str
    description: str = None
    domain: str = None
    entrypoint: str = None
    """When "entrypoint" is set it should point to a service in the "services" list that has an image"""
    services: List[Service] = []


class PingPayload(WebhookCommonPayload):

    zen: str


class WorkflowJobPayload(WebhookCommonPayload):
    class WorkflowJob(BaseModel):
        name: str
        status: str
        conclusion: str | None = None

    workflow_job: WorkflowJob
