import subprocess

from lib.proxy import reload_proxy, write_nginx
from lib.upstream import update_upstreams, write_upstreams


def update_repo():
    """Update the local git repo"""
    # execute a git pull with python in the root of this project:
    subprocess.Popen(["git", "pull"], cwd=".").wait()
    write_nginx()
    write_upstreams()
    update_upstreams()
    reload_proxy()
