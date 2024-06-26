import os
from logging import debug, info
from typing import Callable

from lib.models import Plugin
from lib.proxy import get_domains
from lib.utils import run_command


def get_certs(filter: Callable[[Plugin], bool] = None) -> bool:
    """Get certificates for all or one project"""
    email = os.getenv("LETSENCRYPT_EMAIL")
    if email is None:
        raise ValueError("LETSENCRYPT_EMAIL environment variable is not set")
    domains = get_domains(filter)
    debug("Getting certificates" + (" for project(s)" + ", ".join(domains)) if filter else "")
    change_file = "/data/changed"
    changed = False

    info(f"Running certbot on domains: {' '.join(domains)}")
    for domain in domains:
        # Run certbot command inside docker
        command = [
            "docker",
            "run",
            "--rm",
            "--name",
            "certbot",
            "-v",
            "./data:/data",
            "-v",
            "./certs:/certs",
            "certbot/certbot",
            "certonly",
            "-d",
            domain,
            "--webroot",
            "--webroot-path=/data/certbot",
            "--email",
            email,
            "--agree-tos",
            "--no-eff-email",
            "--non-interactive",
            "--config-dir",
            "/data/letsencrypt",
            "--work-dir",
            "/data/letsencrypt",
            "--logs-dir",
            "/data/letsencrypt",
            "--post-hook",
            f"mkdir -p /certs/{domain} && \
                cp -L /data/letsencrypt/live/{domain}/fullchain.pem /certs/{domain}/fullchain.pem && \
                cp -L /data/letsencrypt/live/{domain}/privkey.pem /certs/{domain}/privkey.pem && \
                chown -R 101:101 /certs/{domain} && touch {change_file} && chmod a+wr {change_file}",
        ]
        staging = os.getenv("LETSENCRYPT_STAGING")
        if not staging is None:
            command.append("--staging")
        run_command(command)

        # Check if certificates have changed
        if os.path.isfile("." + change_file):
            changed = True
            info(f"Certificates for {domain} have been updated")
            os.remove("." + change_file)

    return changed
