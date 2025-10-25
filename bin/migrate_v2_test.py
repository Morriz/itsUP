#!.venv/bin/python
"""Tests for migrate-v2.py"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Import the module
import importlib.util
spec = importlib.util.spec_from_file_location("migrate_v2", "bin/migrate-v2.py")
migrate_v2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migrate_v2)


class TestMigrateInfrastructure(unittest.TestCase):
    """Test infrastructure migration"""

    def test_migrate_infrastructure_basic(self):
        """Test basic infrastructure migration"""
        db = {
            'domain_suffix': 'example.com',
            'letsencrypt': {'email': 'admin@example.com'},
            'trusted_ips': ['192.168.1.1'],
            'traefik': {'log_level': 'INFO'},
        }

        with patch.object(migrate_v2, 'replace_secrets_with_vars', side_effect=lambda x: x):
            infra = migrate_v2.migrate_infrastructure(db)

        self.assertEqual(infra['domain_suffix'], 'example.com')
        self.assertEqual(infra['letsencrypt']['email'], 'admin@example.com')
        self.assertEqual(infra['trusted_ips'], ['192.168.1.1'])
        self.assertEqual(infra['traefik']['log_level'], 'INFO')

    def test_migrate_infrastructure_partial(self):
        """Test infrastructure migration with partial fields"""
        db = {
            'domain_suffix': 'example.com',
            'projects': [{'name': 'test'}]  # Should be ignored
        }

        with patch.object(migrate_v2, 'replace_secrets_with_vars', side_effect=lambda x: x):
            infra = migrate_v2.migrate_infrastructure(db)

        self.assertEqual(infra['domain_suffix'], 'example.com')
        self.assertNotIn('projects', infra)


class TestReplaceSecretsWithVars(unittest.TestCase):
    """Test secret replacement logic"""

    def test_replace_secrets_no_secrets_file(self):
        """Test secret replacement when secrets file doesn't exist"""
        data = {'key': 'value'}
        result = migrate_v2.replace_secrets_with_vars(data)
        self.assertEqual(result, {'key': 'value'})

    @patch('builtins.open', create=True)
    @patch('pathlib.Path.exists')
    def test_replace_secrets_with_secrets(self, mock_exists, mock_open):
        """Test secret replacement with secrets file"""
        mock_exists.return_value = True
        mock_open.return_value.__enter__.return_value.readlines = MagicMock(
            return_value=['KEY1=secret123\n', '# comment\n', 'KEY2=pass456\n']
        )
        mock_open.return_value.__enter__.return_value.__iter__ = MagicMock(
            return_value=iter(['KEY1=secret123\n', '# comment\n', 'KEY2=pass456\n'])
        )

        data = {
            'password': 'secret123',
            'nested': {'token': 'pass456'},
            'list': ['secret123', 'normal']
        }

        result = migrate_v2.replace_secrets_with_vars(data)

        self.assertEqual(result['password'], '${KEY1}')
        self.assertEqual(result['nested']['token'], '${KEY2}')
        self.assertEqual(result['list'], ['${KEY1}', 'normal'])

    @patch('builtins.open', side_effect=IOError("File error"))
    @patch('pathlib.Path.exists')
    def test_replace_secrets_io_error(self, mock_exists, mock_open):
        """Test secret replacement handles IO errors gracefully"""
        mock_exists.return_value = True

        data = {'key': 'value'}
        result = migrate_v2.replace_secrets_with_vars(data)

        # Should return original data without replacement
        self.assertEqual(result, {'key': 'value'})


class TestMigrateProjectTraefikConfig(unittest.TestCase):
    """Test project traefik config migration"""

    def test_migrate_project_traefik_basic(self):
        """Test basic project traefik config migration"""
        project = {
            'name': 'test-project',
            'enabled': True,
            'services': [
                {
                    'host': 'web',
                    'ingress': [
                        {
                            'domain': 'example.com',
                            'port': 80,
                            'router': 'http'
                        }
                    ]
                }
            ]
        }

        with patch.object(migrate_v2, 'replace_secrets_with_vars', side_effect=lambda x: x):
            traefik = migrate_v2.migrate_project_traefik_config(project)

        self.assertEqual(traefik['enabled'], True)
        self.assertEqual(len(traefik['ingress']), 1)
        self.assertEqual(traefik['ingress'][0]['service'], 'web')
        self.assertEqual(traefik['ingress'][0]['domain'], 'example.com')
        self.assertEqual(traefik['ingress'][0]['port'], 80)

    def test_migrate_project_missing_name(self):
        """Test project migration fails with missing name"""
        project = {'services': []}

        with self.assertRaises(ValueError) as cm:
            migrate_v2.migrate_project_traefik_config(project)

        self.assertIn("missing required 'name' field", str(cm.exception))

    def test_migrate_project_with_tls_sans(self):
        """Test project with TLS SANs"""
        project = {
            'name': 'test',
            'services': [
                {
                    'host': 'web',
                    'ingress': [
                        {
                            'domain': 'example.com',
                            'port': 443,
                            'tls': {'sans': ['www.example.com', 'api.example.com']}
                        }
                    ]
                }
            ]
        }

        with patch.object(migrate_v2, 'replace_secrets_with_vars', side_effect=lambda x: x):
            traefik = migrate_v2.migrate_project_traefik_config(project)

        self.assertEqual(traefik['ingress'][0]['tls_sans'], ['www.example.com', 'api.example.com'])


class TestValidateProjectName(unittest.TestCase):
    """Test project name validation"""

    def test_valid_project_name(self):
        """Test valid project names"""
        self.assertEqual(migrate_v2.validate_project_name('my-project'), 'my-project')
        self.assertEqual(migrate_v2.validate_project_name('project123'), 'project123')
        self.assertEqual(migrate_v2.validate_project_name('my_project'), 'my_project')

    def test_invalid_project_name_path_traversal(self):
        """Test project name with path traversal"""
        with self.assertRaises(ValueError) as cm:
            migrate_v2.validate_project_name('../etc')
        self.assertIn("cannot contain path separators", str(cm.exception))

        with self.assertRaises(ValueError) as cm:
            migrate_v2.validate_project_name('foo/../bar')
        self.assertIn("cannot contain path separators", str(cm.exception))

    def test_invalid_project_name_special_dirs(self):
        """Test project name with special directory names"""
        with self.assertRaises(ValueError) as cm:
            migrate_v2.validate_project_name('.')
        self.assertIn("Invalid project name", str(cm.exception))

        with self.assertRaises(ValueError) as cm:
            migrate_v2.validate_project_name('..')
        self.assertIn("Invalid project name", str(cm.exception))


class TestCheckFileExists(unittest.TestCase):
    """Test file existence checking"""

    def test_file_does_not_exist(self):
        """Test when file doesn't exist"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / 'nonexistent.txt'
            result = migrate_v2.check_file_exists(path, force=False)
            self.assertTrue(result)

    def test_file_exists_without_force(self):
        """Test when file exists and force=False"""
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            try:
                path = Path(tmp.name)
                result = migrate_v2.check_file_exists(path, force=False)
                self.assertFalse(result)
            finally:
                path.unlink()

    def test_file_exists_with_force(self):
        """Test when file exists and force=True"""
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            try:
                path = Path(tmp.name)
                result = migrate_v2.check_file_exists(path, force=True)
                self.assertTrue(result)
            finally:
                path.unlink()


class TestMainFunction(unittest.TestCase):
    """Test main migration function"""

    @patch('migrate_v2.validate_db')
    @patch('builtins.open', create=True)
    @patch('pathlib.Path.exists')
    def test_main_dry_run(self, mock_exists, mock_open, mock_validate):
        """Test main function in dry-run mode"""
        # Mock file system
        def exists_side_effect(self):
            return str(self) in ['db.yml', 'upstream', 'upstream/test-project/docker-compose.yml']
        mock_exists.side_effect = exists_side_effect

        # Mock db.yml content
        mock_open.return_value.__enter__.return_value.read.return_value = """
projects:
  - name: test-project
    services:
      - host: web
"""

        # Mock argparse
        with patch('sys.argv', ['migrate-v2.py', '--dry-run']):
            result = migrate_v2.main()

        self.assertEqual(result, 0)
        mock_validate.assert_called_once()

    @patch('migrate_v2.validate_db')
    @patch('pathlib.Path.exists')
    def test_main_missing_db_yml(self, mock_exists, mock_validate):
        """Test main function with missing db.yml"""
        mock_exists.return_value = False

        with patch('sys.argv', ['migrate-v2.py']):
            result = migrate_v2.main()

        self.assertEqual(result, 1)

    @patch('migrate_v2.validate_db', side_effect=Exception("Validation failed"))
    def test_main_validation_failure(self, mock_validate):
        """Test main function with validation failure"""
        with patch('sys.argv', ['migrate-v2.py']):
            result = migrate_v2.main()

        self.assertEqual(result, 1)

    @patch('migrate_v2.validate_db')
    @patch('builtins.open', create=True)
    @patch('pathlib.Path.exists')
    def test_main_missing_upstream_dir(self, mock_exists, mock_open, mock_validate):
        """Test main function with missing upstream/ directory"""
        # Mock file system - db.yml exists but upstream/ doesn't
        def exists_side_effect(self):
            path_str = str(self)
            if path_str == 'db.yml':
                return True
            if path_str == 'upstream':
                return False
            return False
        mock_exists.side_effect = exists_side_effect

        # Mock db.yml content
        mock_open.return_value.__enter__.return_value.read.return_value = """
projects:
  - name: test-project
"""

        with patch('sys.argv', ['migrate-v2.py']):
            result = migrate_v2.main()

        self.assertEqual(result, 1)

    @patch('migrate_v2.validate_db')
    @patch('yaml.safe_load', return_value="invalid")
    @patch('builtins.open', create=True)
    @patch('pathlib.Path.exists')
    def test_main_invalid_yaml(self, mock_exists, mock_open, mock_yaml, mock_validate):
        """Test main function with invalid YAML (not a dict)"""
        mock_exists.return_value = True

        with patch('sys.argv', ['migrate-v2.py']):
            result = migrate_v2.main()

        self.assertEqual(result, 1)


if __name__ == '__main__':
    unittest.main()
