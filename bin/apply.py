#!/usr/bin/env python3

import os
import sys

from dotenv import load_dotenv

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from lib.logging_config import setup_logging
from lib.proxy import update_proxy, write_proxies
from lib.upstream import update_upstreams, write_upstreams

load_dotenv()

if __name__ == "__main__":
    setup_logging()

    write_proxies()
    write_upstreams()

    # Update with zero-downtime (auto-detects changes)
    update_proxy()
    update_upstreams()
