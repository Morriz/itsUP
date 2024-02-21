#!.venv/bin/python

import os
import sys

from dotenv import load_dotenv

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from lib.certs import get_certs
from lib.proxy import reload_proxy, write_proxies
from lib.upstream import update_upstreams, write_upstreams

load_dotenv()

if __name__ == "__main__":
    # if any argument is passed, we also do a rollout
    rollout = bool(sys.argv[1]) if len(sys.argv) > 1 else False
    get_certs()
    write_proxies()
    write_upstreams()
    update_upstreams(rollout)
    reload_proxy()
