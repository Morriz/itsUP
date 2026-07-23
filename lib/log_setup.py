"""Logging setup for daemon processes whose supervisor captures stdout."""

import logging
import os
import sys


def configure_daemon_logging() -> None:
    """Route daemon diagnostics to stdout with itsUP's existing level split."""
    project_level = os.environ.get("ITSUP_LOG_LEVEL", os.environ.get("LOG_LEVEL", "INFO"))
    third_party_level = os.environ.get("ITSUP_THIRD_PARTY_LOG_LEVEL", "WARNING")

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(levelname)s %(name)s %(message)s"))
    root_logger.addHandler(handler)
    root_logger.setLevel(third_party_level)
    logging.getLogger("itsup").setLevel(project_level)
