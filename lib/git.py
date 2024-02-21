import os

from dotenv import load_dotenv

from lib.proxy import reload_proxy, write_proxies
from lib.upstream import update_upstreams, write_upstreams
from lib.utils import run_command

load_dotenv()


def update_repo() -> None:
    """Update the local git repo"""
    # execute a git pull with python in the root of this project:
    if os.environ["PYTHON_ENV"] == "production":
        run_command("git fetch origin main".split(" "), cwd=".")
        run_command("git reset --hard origin/main".split(" "), cwd=".")
    write_proxies()
    write_upstreams()
    update_upstreams()
    reload_proxy()
    # restart the api to make sure the new code is running:
    run_command(["bin/start-api.sh"])
