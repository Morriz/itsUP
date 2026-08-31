"""Shared test fixtures for a temporary itsUP repository root."""

import os
import shutil
import tempfile
import unittest
from pathlib import Path


class TemporaryItsupRootTestCase(unittest.TestCase):
    """Provide an isolated, fail-closed itsUP root for each test."""

    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp())
        self._previous_root = os.environ.get("ITSUP_ROOT")
        os.environ["ITSUP_ROOT"] = str(self.root)

    def tearDown(self) -> None:
        if self._previous_root is None:
            os.environ.pop("ITSUP_ROOT", None)
        else:
            os.environ["ITSUP_ROOT"] = self._previous_root
        shutil.rmtree(self.root)
