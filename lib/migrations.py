import logging
import tomllib
from pathlib import Path

from ruamel.yaml import YAML

logger = logging.getLogger(__name__)


def get_schema_version() -> str:
    """Get current schema version from projects/itsup.yml"""
    itsup_file = Path("projects/itsup.yml")
    if not itsup_file.exists():
        return "1.0.0"

    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.default_flow_style = False

    with open(itsup_file) as f:
        config = yaml.load(f) or {}

    return config.get("schemaVersion", "1.0.0")


def set_schema_version(version: str) -> None:
    """Update schema version in projects/itsup.yml"""
    itsup_file = Path("projects/itsup.yml")

    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.default_flow_style = False

    with open(itsup_file) as f:
        config = yaml.load(f) or {}

    config["schemaVersion"] = version

    with open(itsup_file, "w") as f:
        yaml.dump(config, f)


def get_app_version() -> str:
    """Get app version from pyproject.toml (MAJOR.MINOR only)"""
    with open("pyproject.toml", "rb") as f:
        config = tomllib.load(f)

    version = config["project"]["version"]
    parts = version.split(".")
    major = parts[0] if len(parts) > 0 else "0"
    minor = parts[1] if len(parts) > 1 else "0"
    return f"{major}.{minor}.0"


def migrate(dry_run: bool = False, list_only: bool = False) -> bool:
    """Run all pending migrations.

    Args:
        dry_run: If True, show what would change without making changes
        list_only: If True, only list which fixers would run

    Returns:
        True if migrations were applied, False if nothing to do
    """
    from lib.fixers import FIXERS_V2_1

    schema_version = get_schema_version()
    app_version = get_app_version()

    if schema_version >= app_version:
        logger.info(f"Schema already up to date (v{schema_version})")
        return False

    logger.info(f"Current schema version: {schema_version}")
    logger.info(f"Target version: {app_version}")

    if list_only:
        logger.info(f"\nPending migrations ({len(FIXERS_V2_1)} fixers):")
        for i, fixer in enumerate(FIXERS_V2_1, 1):
            logger.info(f"  [{i}/{len(FIXERS_V2_1)}] {fixer.__name__.replace('_', ' ').title()}")
        return True

    projects_dir = Path("projects")

    for i, fixer in enumerate(FIXERS_V2_1, 1):
        logger.info(f"[{i}/{len(FIXERS_V2_1)}] Running {fixer.__name__}")
        result = fixer.apply(projects_dir, dry_run=dry_run)

        if result.get("errors"):
            logger.error(f"Errors in {fixer.__name__}:")
            for error in result["errors"]:
                logger.error(f"  - {error}")
            return False

    if not dry_run:
        set_schema_version(app_version)
        logger.info(f"✓ Updated schema version to {app_version}")

        # Run validation after migration
        from lib.data import validate_all

        logger.info("\nValidating migrated configurations...")
        all_errors = validate_all()
        if all_errors:
            logger.error(f"✗ {len(all_errors)} project(s) with validation errors:")
            for proj, errors in all_errors.items():
                logger.error(f"\n{proj}:")
                for error in errors:
                    logger.error(f"  - {error}")
            return False
        else:
            logger.info("✓ All projects valid")

    logger.info("Migration complete!")
    return True
