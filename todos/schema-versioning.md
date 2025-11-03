# Schema Versioning & Migration System

## Overview

Simple migration system to handle schema changes between itsUP versions. Users run `itsup migrate` to upgrade their configuration to the latest schema format.

## Design Principles

1. **Simple** - Collection of idempotent fixers, not complex migration framework
2. **Explicit** - User must run `itsup migrate`, not automatic
3. **Git-aware** - Use `git mv` for file renames to preserve history
4. **Safe** - Dry-run mode, idempotent checks, clear confirmations
5. **Forward-only** - No rollback support (keep it simple)

## Version Tracking

### Schema Version Field

Add to `projects/itsup.yml`:

```yaml
# itsUP infrastructure configuration
schemaVersion: "2.1.0"  # NEW FIELD
routerIP: 192.168.1.1
backup:
  enabled: true
  # ...
```

### Version Sources

- **Schema version**: `projects/itsup.yml` → `schemaVersion` field
- **App version**: `pyproject.toml` → `version` field (MAJOR.MINOR.PATCH)

### Comparison Logic

Only compare MAJOR.MINOR (ignore PATCH):
- Schema v2.1.x → compatible with app v2.1.y
- Schema v2.0.x → incompatible with app v2.1.y (needs migration)

## Command Interface

### Primary Command

```bash
itsup migrate              # Run all pending fixers
itsup migrate --dry-run    # Show what would change
itsup migrate --list       # Show which fixers would run
```

### Migration Flow

1. **Check current schema version** from `projects/itsup.yml`
2. **Compare to app version** from `pyproject.toml`
3. **Identify needed fixers** (schema < app)
4. **Run fixers in order** (each is idempotent)
5. **Update schema version** in `projects/itsup.yml`

### Example Output

```bash
$ itsup migrate --dry-run
Current schema version: 2.0.0
Target version: 2.1.0

Pending migrations:
  [1/2] Rename ingress.yml → itsup-project.yml (16 files)
  [2/2] Validate egress format (project:service)

Run 'itsup migrate' to apply changes.

$ itsup migrate
Current schema version: 2.0.0
Target version: 2.1.0

Running migrations:
  ✓ Renamed 16 files: ingress.yml → itsup-project.yml
  ✓ Validated egress format (all valid)
  ✓ Updated schema version to 2.1.0

Migration complete!
```

## Fixer Implementation Pattern

### File Structure

```
lib/
  migrations.py          # Main migration orchestrator
  fixers/
    __init__.py
    rename_ingress.py    # Fixer: ingress.yml → itsup-project.yml
    validate_egress.py   # Fixer: check egress format
```

### Fixer Interface

Each fixer is an idempotent function:

```python
# lib/fixers/rename_ingress.py
from pathlib import Path
import subprocess
import logging

logger = logging.getLogger(__name__)

def apply(projects_dir: Path, dry_run: bool = False) -> dict:
    """Rename ingress.yml to itsup-project.yml in all projects.

    Returns:
        {
            "renamed": ["project1", "project2"],
            "skipped": ["project3"],  # Already has itsup-project.yml
            "errors": []
        }
    """
    renamed = []
    skipped = []
    errors = []

    for project_dir in projects_dir.iterdir():
        if not project_dir.is_dir() or project_dir.name.startswith('.'):
            continue

        old_file = project_dir / "ingress.yml"
        new_file = project_dir / "itsup-project.yml"

        # Idempotent check
        if not old_file.exists():
            continue  # No old file
        if new_file.exists():
            skipped.append(project_dir.name)
            continue  # Already migrated

        if dry_run:
            renamed.append(project_dir.name)
            logger.info(f"Would rename: {old_file} → {new_file}")
            continue

        # Check if projects/ is a git repo
        try:
            is_git_repo = (projects_dir / ".git").exists()

            if is_git_repo:
                # Use git mv to preserve history
                subprocess.run(
                    ["git", "mv", str(old_file), str(new_file)],
                    cwd=projects_dir,
                    check=True
                )
            else:
                # Regular rename
                old_file.rename(new_file)

            renamed.append(project_dir.name)
            logger.info(f"✓ Renamed: {project_dir.name}/ingress.yml → itsup-project.yml")

        except Exception as e:
            errors.append(f"{project_dir.name}: {e}")
            logger.error(f"! Failed to rename {project_dir.name}: {e}")

    return {"renamed": renamed, "skipped": skipped, "errors": errors}
```

### Migration Orchestrator

```python
# lib/migrations.py
from pathlib import Path
import logging
import yaml

from lib.fixers import rename_ingress, validate_egress

logger = logging.getLogger(__name__)

# Fixers in order (v2.0 → v2.1)
FIXERS_V2_1 = [
    rename_ingress,
    validate_egress,
]

def get_schema_version() -> str:
    """Get current schema version from projects/itsup.yml"""
    itsup_file = Path("projects/itsup.yml")
    if not itsup_file.exists():
        return "1.0.0"  # Assume old version if missing

    with open(itsup_file) as f:
        config = yaml.safe_load(f) or {}

    return config.get("schemaVersion", "1.0.0")

def set_schema_version(version: str):
    """Update schema version in projects/itsup.yml"""
    itsup_file = Path("projects/itsup.yml")

    with open(itsup_file) as f:
        config = yaml.safe_load(f) or {}

    config["schemaVersion"] = version

    with open(itsup_file, "w") as f:
        yaml.dump(config, f, sort_keys=False)

def get_app_version() -> str:
    """Get app version from pyproject.toml (MAJOR.MINOR only)"""
    import tomllib

    with open("pyproject.toml", "rb") as f:
        config = tomllib.load(f)

    version = config["project"]["version"]
    major, minor, _ = version.split(".")
    return f"{major}.{minor}.0"

def migrate(dry_run: bool = False) -> bool:
    """Run all pending migrations.

    Returns:
        True if migrations were applied, False if nothing to do
    """
    schema_version = get_schema_version()
    app_version = get_app_version()

    if schema_version >= app_version:
        logger.info(f"Schema already up to date (v{schema_version})")
        return False

    logger.info(f"Current schema version: {schema_version}")
    logger.info(f"Target version: {app_version}")

    projects_dir = Path("projects")

    # Run fixers
    for i, fixer in enumerate(FIXERS_V2_1, 1):
        logger.info(f"[{i}/{len(FIXERS_V2_1)}] Running {fixer.__name__}")
        result = fixer.apply(projects_dir, dry_run=dry_run)

        if result["errors"]:
            logger.error(f"Errors in {fixer.__name__}:")
            for error in result["errors"]:
                logger.error(f"  - {error}")
            return False  # Stop on errors

    if not dry_run:
        set_schema_version(app_version)
        logger.info(f"✓ Updated schema version to {app_version}")

    logger.info("Migration complete!")
    return True
```

## Version Checking

Add to all commands:

```python
# lib/version_check.py
def check_schema_version():
    """Check if schema version matches app version.

    Raises SystemExit if migration needed.
    """
    from lib.migrations import get_schema_version, get_app_version

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

# In each command (commands/apply.py, etc.)
from lib.version_check import check_schema_version

def apply(args):
    check_schema_version()  # Check before running
    # ... rest of command
```

## Current Migrations Needed

### v2.0 → v2.1

**Fixer 1: Rename ingress.yml → itsup-project.yml**
- Finds all `projects/*/ingress.yml` files
- Renames to `itsup-project.yml` using `git mv` if in git repo
- Skips if `itsup-project.yml` already exists (idempotent)

**Fixer 2: Validate egress format**
- No changes, just validates egress uses `project:service` format
- Warns if old format detected

## Bootstrap: Adding schemaVersion

### First-Time Users

`itsup init` should create `projects/itsup.yml` with:

```yaml
schemaVersion: "2.1.0"  # Current version
routerIP: auto-detect
```

### Existing Users

When `schemaVersion` field is missing:
1. Assume schema v1.0.0 (old format)
2. Show message: "Run 'itsup migrate' to upgrade configuration"
3. Exit with error

## Implementation Checklist

- [ ] Add `schemaVersion` field to samples/itsup.yml
- [ ] Create lib/migrations.py orchestrator
- [ ] Create lib/fixers/ directory
- [ ] Implement rename_ingress.py fixer
- [ ] Implement validate_egress.py fixer
- [ ] Create lib/version_check.py
- [ ] Add check_schema_version() to all commands
- [ ] Create commands/migrate.py command
- [ ] Update itsup init to add schemaVersion field
- [ ] Add migration tests
- [ ] Document in README.md

## Future Enhancements (Only If Needed)

- **Rollback support** - Reverse migrations (2x complexity)
- **Per-project versions** - Track schema per project vs global (complex)
- **Migration history** - Log which migrations ran when (auditability)
- **Pluggable fixers** - User-defined migration scripts (extensibility)

## Open Questions

1. **Semver rules** - Bump MINOR on schema changes, PATCH on bug fixes?
   - **Recommendation**: Yes, strict semver for schema changes

2. **Multiple app versions** - Support migrating from any old version?
   - **Recommendation**: Yes, fixers should handle any starting state

3. **Failed migrations** - Rollback partial changes?
   - **Recommendation**: No, require manual fix (simpler)

4. **Git conflicts** - What if `git mv` fails due to unstaged changes?
   - **Recommendation**: Show error, ask user to commit/stash first

## Examples

### Happy Path

```bash
# User on old version
$ itsup apply
ERROR: Your config schema (v2.0.0) is older than itsUP (v2.1.0)
Run 'itsup migrate' to upgrade your configuration.

# Check what would change
$ itsup migrate --dry-run
Current schema version: 2.0.0
Target version: 2.1.0

Pending migrations:
  [1/2] Rename ingress.yml → itsup-project.yml (16 files)
  [2/2] Validate egress format

# Apply migrations
$ itsup migrate
✓ Renamed 16 files
✓ Validated egress format
✓ Updated schema version to 2.1.0

# Now can use itsup normally
$ itsup apply
✓ Applied all projects
```

### Edge Cases

```bash
# Already migrated
$ itsup migrate
Schema already up to date (v2.1.0)

# Partial migration (some files already renamed)
$ itsup migrate
[1/2] Rename ingress.yml → itsup-project.yml
  ✓ Renamed: project1, project2
  → Skipped: project3 (already has itsup-project.yml)

# Git repo with uncommitted changes
$ itsup migrate
ERROR: Cannot migrate - you have uncommitted changes in projects/
Commit or stash your changes first, then run 'itsup migrate'
```

## References

- Main implementation plan: `todos/ingress-rework.md`
- Egress network segmentation design (Phase 3 config rename)
