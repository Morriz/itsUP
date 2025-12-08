#!/usr/bin/env python3

import subprocess
import tempfile
import unittest
from pathlib import Path

from lib.fixers.rename_ingress import apply, get_git_env


class TestRenameIngress(unittest.TestCase):
    """Integration tests for rename_ingress fixer"""

    def setUp(self) -> None:
        """Set up temporary test directory"""
        self.temp_dir = tempfile.mkdtemp()
        self.projects_dir = Path(self.temp_dir) / "projects"
        self.projects_dir.mkdir()

    def tearDown(self) -> None:
        """Clean up temporary directory"""
        import shutil

        shutil.rmtree(self.temp_dir)

    def _create_project_with_ingress(self, project_name: str) -> None:
        """Helper to create a project with ingress.yml"""
        project_dir = self.projects_dir / project_name
        project_dir.mkdir()
        (project_dir / "ingress.yml").write_text("enabled: true\n")

    def _create_project_with_itsup_project(self, project_name: str) -> None:
        """Helper to create a project with itsup-project.yml (already migrated)"""
        project_dir = self.projects_dir / project_name
        project_dir.mkdir()
        (project_dir / "itsup-project.yml").write_text("enabled: true\n")

    def _init_git_repo(self) -> None:
        """Initialize git repository in projects dir"""
        git_env = get_git_env()
        subprocess.run(["git", "init"], cwd=self.projects_dir, check=True, capture_output=True, env=git_env)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=self.projects_dir,
            check=True,
            capture_output=True,
            env=git_env,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=self.projects_dir,
            check=True,
            capture_output=True,
            env=git_env,
        )
        subprocess.run(["git", "add", "."], cwd=self.projects_dir, check=True, capture_output=True, env=git_env)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=self.projects_dir,
            check=True,
            capture_output=True,
            env=git_env,
        )

    def test_rename_without_git(self) -> None:
        """Test renaming files without git (plain filesystem rename)"""
        self._create_project_with_ingress("project1")
        self._create_project_with_ingress("project2")

        result = apply(self.projects_dir, dry_run=False)

        self.assertEqual(result["renamed"], ["project1", "project2"])
        self.assertEqual(result["skipped"], [])
        self.assertEqual(result["errors"], [])

        # Verify files were renamed
        self.assertFalse((self.projects_dir / "project1" / "ingress.yml").exists())
        self.assertTrue((self.projects_dir / "project1" / "itsup-project.yml").exists())
        self.assertFalse((self.projects_dir / "project2" / "ingress.yml").exists())
        self.assertTrue((self.projects_dir / "project2" / "itsup-project.yml").exists())

    def test_rename_with_git(self) -> None:
        """Test renaming files with git (uses git mv to preserve history)"""
        self._create_project_with_ingress("project1")
        self._create_project_with_ingress("project2")
        self._init_git_repo()

        result = apply(self.projects_dir, dry_run=False)

        self.assertEqual(result["renamed"], ["project1", "project2"])
        self.assertEqual(result["skipped"], [])
        self.assertEqual(result["errors"], [])

        # Verify files were renamed
        self.assertFalse((self.projects_dir / "project1" / "ingress.yml").exists())
        self.assertTrue((self.projects_dir / "project1" / "itsup-project.yml").exists())
        self.assertFalse((self.projects_dir / "project2" / "ingress.yml").exists())
        self.assertTrue((self.projects_dir / "project2" / "itsup-project.yml").exists())

        # Verify git tracked the rename
        git_result = subprocess.run(
            ["git", "status", "--short"],
            cwd=self.projects_dir,
            capture_output=True,
            text=True,
            check=True,
            env=get_git_env(),
        )
        # Git should show renamed files
        self.assertIn("R", git_result.stdout)  # R = renamed

    def test_skip_already_migrated(self) -> None:
        """Test skipping projects that already have itsup-project.yml"""
        self._create_project_with_ingress("project1")
        self._create_project_with_itsup_project("project2")
        project3_dir = self.projects_dir / "project3"
        project3_dir.mkdir()
        (project3_dir / "ingress.yml").write_text("enabled: true\n")
        (project3_dir / "itsup-project.yml").write_text("enabled: true\n")  # Both files

        result = apply(self.projects_dir, dry_run=False)

        self.assertEqual(sorted(result["renamed"]), ["project1"])
        self.assertEqual(sorted(result["skipped"]), ["project3"])
        self.assertEqual(result["errors"], [])

    def test_skip_projects_without_ingress(self) -> None:
        """Test skipping projects that don't have ingress.yml"""
        project_dir = self.projects_dir / "project1"
        project_dir.mkdir()
        (project_dir / "docker-compose.yml").write_text("services: {}\n")

        result = apply(self.projects_dir, dry_run=False)

        self.assertEqual(result["renamed"], [])
        self.assertEqual(result["skipped"], [])
        self.assertEqual(result["errors"], [])

    def test_dry_run(self) -> None:
        """Test dry-run mode doesn't modify files"""
        self._create_project_with_ingress("project1")

        result = apply(self.projects_dir, dry_run=True)

        self.assertEqual(result["renamed"], ["project1"])
        self.assertEqual(result["skipped"], [])
        self.assertEqual(result["errors"], [])

        # Verify files were NOT renamed
        self.assertTrue((self.projects_dir / "project1" / "ingress.yml").exists())
        self.assertFalse((self.projects_dir / "project1" / "itsup-project.yml").exists())

    def test_idempotent(self) -> None:
        """Test running fixer multiple times is safe (idempotent)"""
        self._create_project_with_ingress("project1")

        # First run
        result1 = apply(self.projects_dir, dry_run=False)
        self.assertEqual(result1["renamed"], ["project1"])

        # Second run (should skip)
        result2 = apply(self.projects_dir, dry_run=False)
        self.assertEqual(result2["renamed"], [])
        self.assertEqual(result2["skipped"], [])
        self.assertEqual(result2["errors"], [])

    def test_ignore_dotfiles_and_special_dirs(self) -> None:
        """Test ignoring hidden directories"""
        self._create_project_with_ingress("project1")
        (self.projects_dir / ".hidden").mkdir()
        (self.projects_dir / ".config").mkdir()

        result = apply(self.projects_dir, dry_run=False)

        # Should only process project1, ignore dotfiles
        self.assertEqual(result["renamed"], ["project1"])


if __name__ == "__main__":
    unittest.main()
