#!/usr/bin/env python3

import unittest
from pathlib import Path
from unittest.mock import patch

from lib.migrations import (
    get_app_version,
    get_schema_version,
    migrate,
    set_schema_version,
)
from lib.test_support import TemporaryItsupRootTestCase


class TestMigrations(TemporaryItsupRootTestCase):
    """Tests for migration system"""

    def setUp(self) -> None:
        super().setUp()
        (self.root / "pyproject.toml").write_text('[project]\nversion = "2.1.0"\n')
        (self.root / "projects").mkdir()

    @property
    def _itsup_file(self) -> Path:
        return self.root / "projects" / "itsup.yml"

    def test_get_app_version(self) -> None:
        """Test getting app version from pyproject.toml"""
        version = get_app_version()
        self.assertEqual(version, "2.1.0")  # MAJOR.MINOR.0

    def test_get_schema_version_missing_file(self) -> None:
        """Test getting schema version when file doesn't exist"""
        # No projects/itsup.yml under the temp root.
        version = get_schema_version()
        self.assertEqual(version, "1.0.0")  # Default

    def test_get_schema_version_missing_field(self) -> None:
        """Test getting schema version when field is missing"""
        self._itsup_file.write_text("# Config without schemaVersion\nrouterIP: 192.168.1.1\n")

        version = get_schema_version()
        self.assertEqual(version, "1.0.0")  # Default

    def test_set_schema_version(self) -> None:
        """Test setting schema version"""
        self._itsup_file.write_text("schemaVersion: '1.0.0'\nrouterIP: 192.168.1.1\n")

        set_schema_version("2.1.0")

        content = self._itsup_file.read_text()
        self.assertIn("schemaVersion: '2.1.0'", content)
        self.assertIn("routerIP: 192.168.1.1", content)

    @patch("lib.migrations.get_app_version")
    @patch("lib.migrations.get_schema_version")
    def test_migrate_already_up_to_date(
        self, mock_get_schema: unittest.mock.Mock, mock_get_app: unittest.mock.Mock
    ) -> None:
        """Test migration when schema is already up to date"""
        mock_get_schema.return_value = "2.1.0"
        mock_get_app.return_value = "2.1.0"

        result = migrate(dry_run=False)

        self.assertFalse(result)  # Nothing to do

    @patch("lib.migrations.get_app_version")
    @patch("lib.migrations.get_schema_version")
    def test_migrate_list_only(self, mock_get_schema: unittest.mock.Mock, mock_get_app: unittest.mock.Mock) -> None:
        """Test migration with list_only flag"""
        mock_get_schema.return_value = "1.0.0"
        mock_get_app.return_value = "2.1.0"

        result = migrate(list_only=True)

        self.assertTrue(result)  # Returns True to indicate there are migrations


if __name__ == "__main__":
    unittest.main()
