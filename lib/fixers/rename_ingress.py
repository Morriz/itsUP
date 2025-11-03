import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def apply(projects_dir: Path, dry_run: bool = False) -> dict[str, list[str]]:
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
        if not project_dir.is_dir() or project_dir.name.startswith("."):
            continue

        if project_dir.name in ("itsup.yml", "traefik.yml"):
            continue

        old_file = project_dir / "ingress.yml"
        new_file = project_dir / "itsup-project.yml"

        if not old_file.exists():
            continue

        if new_file.exists():
            skipped.append(project_dir.name)
            continue

        if dry_run:
            renamed.append(project_dir.name)
            logger.info(f"Would rename: {old_file} → {new_file}")
            continue

        try:
            is_git_repo = (projects_dir / ".git").exists()

            if is_git_repo:
                # Use relative paths for git mv when running with cwd
                old_rel = f"{project_dir.name}/ingress.yml"
                new_rel = f"{project_dir.name}/itsup-project.yml"
                subprocess.run(
                    ["git", "mv", old_rel, new_rel],
                    cwd=projects_dir,
                    check=True,
                    capture_output=True,
                )
            else:
                old_file.rename(new_file)

            renamed.append(project_dir.name)
            logger.info(f"✓ Renamed: {project_dir.name}/ingress.yml → itsup-project.yml")

        except Exception as e:
            errors.append(f"{project_dir.name}: {e}")
            logger.error(f"! Failed to rename {project_dir.name}: {e}")

    return {"renamed": renamed, "skipped": skipped, "errors": errors}
