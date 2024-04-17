#!.venv/bin/python

import os
import sys

from dotenv import load_dotenv

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from lib.upstream import update_upstream, update_upstreams
from lib.certs import get_certs
from lib.proxy import reload_proxy, rollout_proxy

load_dotenv()

if __name__ == "__main__":
    project = sys.argv[1] if len(sys.argv) > 1 else None
    if project:
        filter = lambda p: p.name == project
        if get_certs(filter):
            if project:
                update_upstream(project, rollout=True)
            else:
                update_upstreams()
