from lib.migrations import get_app_version, get_schema_version


class SchemaVersionError(RuntimeError):
    """The config schema is older than the running itsUP version and needs migration."""


def check_schema_version() -> str | None:
    """Check if schema version matches app version.

    Returns a warning message if the config schema is newer than this itsUP
    version (non-fatal — an operator can act on it, but nothing is broken).

    Raises:
        SchemaVersionError: If the config schema is older than the app version.
    """
    schema_version = get_schema_version()
    app_version = get_app_version()

    if schema_version < app_version:
        raise SchemaVersionError(
            f"Your config schema (v{schema_version}) is older than itsUP (v{app_version})\n"
            f"Run 'itsup migrate' to upgrade your configuration."
        )

    if schema_version > app_version:
        return (
            f"Your config schema (v{schema_version}) is newer than itsUP (v{app_version})\n"
            f"Please upgrade itsUP to the latest version."
        )

    return None
