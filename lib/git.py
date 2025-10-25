import logging
import os
import subprocess

from dotenv import load_dotenv

from bin.write_artifacts import write_upstreams
from lib.data import list_projects
from lib.utils import run_command

load_dotenv()

logger = logging.getLogger(__name__)


def update_repo() -> None:
    """Update the local git repo"""
    # execute a git pull with python in the root of this project:
    if os.environ["PYTHON_ENV"] == "production":
        logger.info("Updating repository from origin/main")
        run_command("git fetch origin main".split(" "), cwd=".")
        run_command("git reset --hard origin/main".split(" "), cwd=".")
        logger.info("Repository updated successfully")

    # Generate all upstream configs
    write_upstreams()

    # Deploy all upstreams
    for project in list_projects():
        upstream_dir = f"upstream/{project}"
        compose_file = f"{upstream_dir}/docker-compose.yml"
        cmd = [
            "docker", "compose",
            "--project-directory", upstream_dir,
            "-p", project,
            "-f", compose_file,
            "up", "-d"
        ]
        subprocess.run(cmd, check=False)  # Don't fail on deployment errors

    # restart the api to make sure the new code is running:
    logger.info("Restarting API server")
    run_command(["bin/start-api.sh"])
