import logging
import sys

logger = logging.getLogger(__name__)


def check_schema_version() -> None:
    """Check if schema version matches app version.

    Raises SystemExit if migration needed.
    """
    from lib.migrations import get_app_version, get_schema_version

    schema_version = get_schema_version()
    app_version = get_app_version()

    if schema_version < app_version:
        logger.error(
            f"Your config schema (v{schema_version}) is older than itsUP (v{app_version})\n"
            f"Run 'itsup migrate' to upgrade your configuration."
        )
        sys.exit(1)

    if schema_version > app_version:
        logger.warning(
            f"Your config schema (v{schema_version}) is newer than itsUP (v{app_version})\n"
            f"Please upgrade itsUP to the latest version."
        )
