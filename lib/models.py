from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


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

    v2 = 2


class Router(str, Enum):
    """Router enum"""

    http = "http"
    tcp = "tcp"
    udp = "udp"


class TLS(BaseModel):
    """TLS model"""

    main: str | None = None
    """The main domain"""
    sans: List[str] = Field(default_factory=list)
    """A list of SANs for the domain"""


class Ingress(BaseModel):
    """Ingress model"""

    service: str | None = None
    """The service name in docker-compose.yml (only used for container projects)"""
    domain: str | None = None
    """The domain to use for the service. If omitted, the service will not be publicly accessible.
    When set TLS termination is done for this domain only."""
    hostport: int | None = None
    """The port to expose on the host"""
    passthrough: bool = False
    """Wether or not traffic to this service is forwarded as-is (without terminating SSL)"""
    path_prefix: str | None = None
    """Should the service be exposed under a specific path?"""
    path_remove: bool = False
    """When set, the path prefix will be removed from the request before forwarding it to the service"""
    port: int = 8080
    """The port to use for the service. If not defined will default to parent service port[idx]"""
    protocol: Protocol = Protocol.tcp
    """The protocol to use for the port"""
    proxyprotocol: ProxyProtocol | None = ProxyProtocol.v2
    """When set, the service is expected to accept the given PROXY protocol version.
    Explicitly set to null to disable."""
    router: Router = Router.http
    """The type of router to use for the service"""
    tls: TLS | None = None
    """TLS settings that will be used instead of 'domain'"""
    expose: bool = False
    """Expose the service to any other internal service"""

    @model_validator(mode="after")
    @classmethod
    def check_passthrough_tcp(cls, data: Any) -> Any:
        if data.passthrough and data.port == 80 and not data.path_prefix == "/.well-known/acme-challenge/":
            raise ValueError("Passthrough is only allowed for ACME challenge on port 80.")
        return data


class Service(BaseModel):
    """Service model"""

    additional_properties: Dict[str, Any] = {}
    """Additional docker compose properties to pass to the service"""
    command: Optional[str] = None
    """The command to run in the service"""
    depends_on: List[str] | Dict[str, Any] = []
    """A list of services to depend on"""
    env: Env = Env()
    """A dictionary of environment variables to pass to the service"""
    host: str
    """The host (name/ip) of the service"""
    image: str = None
    """The full container image uri of the service"""
    ingress: List[Ingress] = None
    """Ingress configuration for the service. If a string is passed,
    it will be used as the domain."""
    labels: List[str] = []
    """Extra labels to add to the service. Should not interfere with
    generated traefik labels for ingress."""
    restart: str = "unless-stopped"
    """The restart policy to use for the service"""
    stateless: bool = False
    """Whether this service is stateless and safe for zero-downtime rollout.
    Stateless services can have multiple instances running simultaneously without
    data corruption. ONLY set to true for services without writable volumes or
    services designed for concurrent multi-instance operation."""
    volumes: List[str] = []
    """A list of volumes to mount in the service"""


class Project(BaseModel):
    """Project model"""

    description: str = None
    """A description of the project"""
    env: Env = None
    """A dictionary of environment variables to pass that the services 
    can use to construct their own vars with, but will not be exposed 
    to the services themselves."""
    enabled: bool = True
    """Wether or not the project is enabled"""
    name: str
    """The name of the project"""
    services: List[Service] = []
    """A list of services to run in the project"""


# V2 Models for projects/ structure


class TraefikConfig(BaseModel):
    """Traefik routing configuration for V2 projects"""

    enabled: bool = True
    """Whether the project is enabled"""
    host: str | None = None
    """External host IP/hostname (for ingress-only projects without containers)"""
    ingress: List[Ingress] = []
    """List of ingress rules"""
    egress: List[str] = []
    """List of target services this project can access (format: project:service)"""
