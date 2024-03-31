from enum import Enum
from gc import enable
from typing import Any, Dict, List

from github_webhooks.schemas import WebhookCommonPayload
from pydantic import BaseModel, ConfigDict


class Env(BaseModel):
    model_config = ConfigDict(extra="allow")


class Plugin(BaseModel):
    """Plugin model"""

    apikey: str = None
    """The API key to use for the plugin, if the plugin requires one"""
    description: str = None
    """A description of the plugin"""
    enabled: bool = False
    """Wether or not the plugin is enabled"""
    name: str = None
    """The name of the plugin"""
    options: Dict[str, Any] = {}
    """A dictionary of options to pass to the plugin"""
    version: str


class PluginCrowdsec(Plugin):
    """Crowdsec plugin model"""

    collections: List[str] = []
    """A list of collections to use for the plugin"""


class PluginRegistry(BaseModel):
    """Plugin registry"""

    crowdsec: PluginCrowdsec


class Protocol(str, Enum):
    """Protocol enum"""

    tcp = "tcp"
    udp = "udp"


class ProxyProtocol(str, Enum):
    """ProxyProtocol enum"""

    v1 = 1
    v2 = 2


class Ingress(BaseModel):
    """Ingress model"""

    domain: str = None
    """The domain to use for the service. If omitted, the service will not be publicly accessible."""
    hostport: int = None
    """The port to expose on the host"""
    passthrough: bool = False
    """Wether or not traffic to this service is forwarded as-is (without terminating SSL)"""
    path_prefix: str = None
    """Should the service be exposed under a specific path?"""
    path_remove: bool = False
    """When set, the path prefix will be removed from the request before forwarding it to the service"""
    port: int = 8080
    """The port to use for the service. If not defined will default to parent service port[idx]"""
    protocol: Protocol = Protocol.tcp
    """The protocol to use for the port"""
    proxyprotocol: ProxyProtocol | None = ProxyProtocol.v2
    """When set, the service is expected to accept the given PROXY protocol version. Explicitly set to null to disable."""


class Service(BaseModel):
    """Service model"""

    additional_properties: Dict[str, Any] = {}
    """Additional docker compose properties to pass to the service"""
    command: str = None
    """The command to run in the service"""
    depends_on: List[str] = []
    """A list of services to depend on"""
    env: Env = None
    """A dictionary of environment variables to pass to the service"""
    image: str = None
    """The full container image uri of the service"""
    ingress: List[Ingress] = []
    """Ingress configuration for the service. If a string is passed, it will be used as the domain."""
    labels: List[str] = []
    """Extra labels to add to the service. Should not interfere with generated traefik labels for ingress."""
    name: str
    """The name of the service"""
    restart: str = "unless-stopped"
    """The restart policy to use for the service"""
    volumes: List[str] = []
    """A list of volumes to mount in the service"""


class Project(BaseModel):
    """Project model"""

    description: str = None
    """A description of the project"""
    env: Env = None
    """A dictionary of environment variables to pass that the services can use to construct their own vars with, but will not be exposed to the services themselves."""
    enabled: bool = True
    """Wether or not the project is enabled"""
    name: str
    """The name of the project"""
    services: List[Service] = []
    """A list of services to run in the project"""


class PingPayload(WebhookCommonPayload):

    zen: str


class WorkflowJobPayload(WebhookCommonPayload):
    class WorkflowJob(BaseModel):
        name: str
        status: str
        conclusion: str | None = None

    workflow_job: WorkflowJob
