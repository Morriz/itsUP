#!.venv/bin/python

import os
import subprocess
import sys

from dotenv import load_dotenv

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from bin.write_artifacts import write_upstreams
from lib.data import list_projects
from lib.logging_config import setup_logging

load_dotenv()


def _build_docker_compose_cmd(project: str) -> list[str]:
    """Build docker compose command for deploying a project."""
    upstream_dir = f"upstream/{project}"
    compose_file = f"{upstream_dir}/docker-compose.yml"
    return [
        "docker",
        "compose",
        "--project-directory",
        upstream_dir,
        "-p",
        project,
        "-f",
        compose_file,
        "up",
        "-d",
    ]


if __name__ == "__main__":
    setup_logging()

    # Generate all upstream configs
    if not write_upstreams():
        sys.exit(1)

    # Deploy all upstreams
    failed_projects = []
    for project in list_projects():
        cmd = _build_docker_compose_cmd(project)
        try:
            subprocess.run(cmd, check=True)
            print(f"✓ {project}")
        except subprocess.CalledProcessError:
            print(f"✗ {project} failed")
            failed_projects.append(project)

    if failed_projects:
        print(f"Failed projects: {', '.join(failed_projects)}")
        sys.exit(1)
