#!.venv/bin/python

import os
import sys

from dotenv import load_dotenv

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from lib.data import validate_db
from lib.logging_config import setup_logging
from lib.proxy import write_proxies
from lib.upstream import write_upstreams

load_dotenv()

if __name__ == "__main__":
    setup_logging()
    validate_db()
    write_proxies()
    write_upstreams()
