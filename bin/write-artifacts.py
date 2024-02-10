#!/usr/bin/env python

import os
import sys

from dotenv import load_dotenv

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from lib.proxy import write_nginx
from lib.upstream import write_upstreams

load_dotenv()

if __name__ == "__main__":
    write_nginx()
    write_upstreams()
