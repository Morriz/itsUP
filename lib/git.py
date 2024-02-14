from lib.proxy import reload_proxy, write_nginx
from lib.upstream import update_upstreams, write_upstreams
from lib.utils import run_command


def update_repo() -> None:
    """Update the local git repo"""
    # execute a git pull with python in the root of this project:
    run_command(["git", "pull"], cwd=".")
    write_nginx()
    write_upstreams()
    update_upstreams()
    reload_proxy()
