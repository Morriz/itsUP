import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from lib.projects import RESERVED_NAMES, create_project, validate_project_name


class TestValidateProjectName(unittest.TestCase):
    """Tests for project name validation."""

    def test_valid_names(self) -> None:
        for name in ["my-app", "redis-cache", "a1", "app", "my-cool-project-123"]:
            validate_project_name(name)  # should not raise

    def test_single_char(self) -> None:
        validate_project_name("a")  # single char is valid

    def test_reserved_names(self) -> None:
        for name in RESERVED_NAMES:
            with self.assertRaises(ValueError, msg=f"'{name}' should be reserved"):
                validate_project_name(name)

    def test_empty(self) -> None:
        with self.assertRaises(ValueError):
            validate_project_name("")

    def test_too_long(self) -> None:
        with self.assertRaises(ValueError):
            validate_project_name("a" * 64)

    def test_max_length_ok(self) -> None:
        validate_project_name("a" * 63)  # exactly 63 is fine

    def test_uppercase(self) -> None:
        with self.assertRaises(ValueError):
            validate_project_name("MyApp")

    def test_leading_hyphen(self) -> None:
        with self.assertRaises(ValueError):
            validate_project_name("-app")

    def test_trailing_hyphen(self) -> None:
        with self.assertRaises(ValueError):
            validate_project_name("app-")

    def test_special_chars(self) -> None:
        for name in ["my_app", "my.app", "my app", "my@app"]:
            with self.assertRaises(ValueError, msg=f"'{name}' should be invalid"):
                validate_project_name(name)


class TestCreateProject(unittest.TestCase):
    """Tests for project scaffolding."""

    def setUp(self) -> None:
        import tempfile

        self._tmpdir = tempfile.mkdtemp()
        self.root = Path(self._tmpdir)
        (self.root / "projects").mkdir()
        (self.root / "secrets").mkdir()

    def tearDown(self) -> None:
        import shutil

        shutil.rmtree(self._tmpdir)

    def test_creates_all_files(self) -> None:
        create_project("my-app", self.root)

        self.assertTrue((self.root / "projects" / "my-app" / "itsup-project.yml").exists())
        self.assertTrue((self.root / "projects" / "my-app" / "docker-compose.yml").exists())
        self.assertTrue((self.root / "secrets" / "my-app.txt").exists())

    def test_itsup_project_yml_valid(self) -> None:
        import yaml

        create_project("my-app", self.root)
        content = yaml.safe_load((self.root / "projects" / "my-app" / "itsup-project.yml").read_text())
        self.assertTrue(content["enabled"])
        self.assertEqual(len(content["ingress"]), 1)
        self.assertEqual(content["ingress"][0]["service"], "my-app-web")
        self.assertEqual(content["ingress"][0]["domain"], "my-app.srv.instrukt.ai")

    def test_rejects_existing_project(self) -> None:
        (self.root / "projects" / "existing").mkdir()
        with self.assertRaises(ValueError):
            create_project("existing", self.root)

    def test_rejects_reserved_name(self) -> None:
        with self.assertRaises(ValueError):
            create_project("dns", self.root)

    def test_skips_existing_secrets_file(self) -> None:
        secret_file = self.root / "secrets" / "my-app.txt"
        secret_file.write_text("EXISTING=secret\n")

        create_project("my-app", self.root)

        # secrets file should not be overwritten
        self.assertEqual(secret_file.read_text(), "EXISTING=secret\n")

    def test_creates_secrets_dir_if_missing(self) -> None:
        import shutil

        shutil.rmtree(self.root / "secrets")
        create_project("my-app", self.root)
        self.assertTrue((self.root / "secrets" / "my-app.txt").exists())


if __name__ == "__main__":
    unittest.main()
