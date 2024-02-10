#!/usr/bin/env python

import os
import sys

from dotenv import load_dotenv

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from lib.certs import get_certs
from lib.proxy import reload_proxy, rollout_proxy

load_dotenv()

if __name__ == "__main__":
    if get_certs():
        rollout_proxy("terminate")
        # reload proxy's terminate service as it needs to get the new upstream
        reload_proxy("terminate")
