#!/usr/bin/env python3

"""Guards the contract that every location itsUP reports is usable from the caller's cwd.

The CLI is installed globally and invoked from anywhere, so a printed
``secrets/foo.txt`` is only correct for a caller standing in the install root.
Locations are therefore resolved through ``lib.paths`` and rendered through
``lib.paths.display_path``; a literal data-tree path in output is a defect.

Two lanes: a behavioral lane that invokes the path-emitting commands from a cwd
outside the install root and asserts every reported location is absolute, and a
structural lane that rejects literal data-tree paths in command source, catching
a new guidance string before anyone runs it.
"""

import ast
import os
import re
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import click
from click.testing import CliRunner

from commands.create import create
from commands.decrypt import decrypt
from commands.edit_secret import edit_secret
from commands.encrypt import encrypt
from commands.projects import projects
from lib.paths import root

# A data-tree path that is not anchored at "/" — i.e. only resolvable from the
# install root. The lookbehind lets absolute paths (".../secrets/x") through.
RELATIVE_DATA_PATH = re.compile(r"(?<![/\w.-])(secrets|projects|upstream)/")

COMMAND_DIR = Path(__file__).resolve().parent


def _assert_no_relative_data_path(case: unittest.TestCase, output: str, label: str) -> None:
    for line in output.splitlines():
        match = RELATIVE_DATA_PATH.search(line)
        case.assertIsNone(
            match,
            f"{label} emitted a location only usable from the install root: {line!r}. "
            f"Resolve it via lib.paths and render it with display_path().",
        )


class TestEmittedLocationsAreCallerUsable(unittest.TestCase):
    """Invoke path-emitting commands from outside the install root."""

    def setUp(self) -> None:
        self.runner = CliRunner()
        sops_available = patch("lib.sops.is_sops_available", return_value=True)
        sops_available.start()
        self.addCleanup(sops_available.stop)
        for module in ("commands.encrypt", "commands.decrypt", "commands.edit_secret"):
            patcher = patch(f"{module}.is_sops_available", return_value=True)
            patcher.start()
            self.addCleanup(patcher.stop)

    def _invoke_outside_root(self, command: click.BaseCommand, args: list[str]) -> str:
        with self.runner.isolated_filesystem() as tmp:
            self.assertNotEqual(Path(tmp).resolve(), root().resolve())
            result = self.runner.invoke(command, args)
        return result.output

    def test_encrypt_missing_name_reports_absolute_location(self) -> None:
        output = self._invoke_outside_root(encrypt, ["definitely-absent-secret"])
        _assert_no_relative_data_path(self, output, "itsup encrypt")

    def test_decrypt_missing_name_reports_absolute_location(self) -> None:
        output = self._invoke_outside_root(decrypt, ["definitely-absent-secret"])
        _assert_no_relative_data_path(self, output, "itsup decrypt")

    def test_edit_secret_non_tty_reports_absolute_locations(self) -> None:
        """The agent-facing branch: edit-secret refuses without a TTY and prints the round trip."""
        output = self._invoke_outside_root(edit_secret, ["definitely-absent-secret"])
        _assert_no_relative_data_path(self, output, "itsup edit-secret")

    def test_edit_secret_missing_encrypted_file_reports_absolute_locations(self) -> None:
        with patch("commands.edit_secret.is_interactive", return_value=True):
            output = self._invoke_outside_root(edit_secret, ["definitely-absent-secret"])
        _assert_no_relative_data_path(self, output, "itsup edit-secret")

    def test_create_next_steps_report_absolute_locations(self) -> None:
        with patch("commands.create.guard_schema_version"), patch("commands.create.create_project"):
            output = self._invoke_outside_root(create, ["scratch-project"])
        _assert_no_relative_data_path(self, output, "itsup create")

    def test_projects_listing_reports_absolute_locations(self) -> None:
        with patch("commands.projects.list_projects", return_value=["some-project"]):
            output = self._invoke_outside_root(projects, ["some-project"])
        _assert_no_relative_data_path(self, output, "itsup projects")


HELP_KEYWORDS = {"help", "short_help", "epilog"}


class TestCommandSourceHasNoLiteralDataPaths(unittest.TestCase):
    """Reject literal data-tree paths in command source, outside help prose.

    Docstrings and Click ``help=``/``short_help=`` text are exempt: they are
    generic documentation of the command, not a resolved location the caller is
    told to act on.
    """

    def test_no_literal_data_path_in_command_strings(self) -> None:
        offenders: list[str] = []

        for source_file in sorted(COMMAND_DIR.glob("*.py")):
            if source_file.name.endswith("_test.py"):
                continue
            tree = ast.parse(source_file.read_text(encoding="utf-8"))
            exempt = {
                ast.get_docstring(node, clean=False)
                for node in ast.walk(tree)
                if isinstance(node, ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
            }
            for node in ast.walk(tree):
                if isinstance(node, ast.keyword) and node.arg in HELP_KEYWORDS:
                    if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                        exempt.add(node.value.value)

            for node in ast.walk(tree):
                if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                    continue
                if node.value in exempt:
                    continue
                if RELATIVE_DATA_PATH.search(node.value):
                    offenders.append(f"{source_file.name}:{node.lineno}: {node.value!r}")

        self.assertEqual(
            offenders,
            [],
            "Literal data-tree paths in command source are only correct from the install root. "
            "Resolve them via lib.paths and render with display_path():\n  " + "\n  ".join(offenders),
        )


if __name__ == "__main__":
    unittest.main()
