#!/usr/bin/env python3

"""DNS stack management (dns-honeypot)"""

from commands.common import create_stack_command
from lib.deploy import deploy_dns_stack
from lib.paths import root

dns = create_stack_command(
    stack_name="dns",
    compose_dir=str(root() / "dns"),
    deploy_func=deploy_dns_stack,
    description="📡 DNS stack management\n\n    Manages the DNS honeypot stack that logs all container DNS queries.\n    This stack MUST be started first as it creates the proxynet network."
)
