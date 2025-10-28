#!/usr/bin/env python3

"""Proxy stack management (Traefik + dockerproxy)"""

from commands.common import create_stack_command
from lib.deploy import deploy_proxy_stack

proxy = create_stack_command(
    stack_name="proxy",
    compose_dir="proxy",
    deploy_func=deploy_proxy_stack,
    description="🔀 Proxy stack management\n\n    Manages the proxy stack (Traefik + dockerproxy + optional CrowdSec)."
)
