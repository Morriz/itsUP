"""Source files never select their own interpreter.

Executable commands come from ``[project.scripts]``, which the installer
generates with the virtualenv interpreter already in the shebang; standalone
jobs are invoked by the virtualenv interpreter. A file that re-execs itself
into a virtualenv duplicates that resolution in every copy, breaks editor
analysis, and drifts from the CLI design contract.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SEARCH_ROOTS = ("api", "bin", "commands", "lib", "monitor", "tools")
FORBIDDEN = ("_VENV_PYTHON", "os.execv", "_os.execv")


def _python_sources() -> list[Path]:
    files: list[Path] = []
    for root in SEARCH_ROOTS:
        directory = REPO_ROOT / root
        if directory.is_dir():
            files.extend(p for p in directory.rglob("*.py") if "__pycache__" not in p.parts)
    return files


def test_no_source_file_re_execs_into_a_virtualenv() -> None:
    offenders = {
        str(path.relative_to(REPO_ROOT)): marker
        for path in _python_sources()
        for marker in FORBIDDEN
        if marker in path.read_text(encoding="utf-8")
    }

    assert not offenders, (
        "Python sources must not select their own interpreter; "
        f"found environment bootstrap markers in: {offenders}. "
        "Add a [project.scripts] entry, or invoke the file with the virtualenv interpreter."
    )
