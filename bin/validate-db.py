#!.venv/bin/python

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from lib.logging_config import setup_logging
from lib.data import validate_db

if __name__ == "__main__":
    setup_logging()
    validate_db()
