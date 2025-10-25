import os
import sys
from pathlib import Path
import unittest
from unittest.mock import MagicMock, Mock, call, mock_open, patch
import yaml

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Import after path setup
# Use 'migrate-v2' module name with hyphen replaced by underscore for import
import importlib.util
spec = importlib.util.spec_from_file_location(
    "migrate_v2",
    os.path.join(os.path.dirname(__file__), "migrate-v2.py")
)
migrate_v2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migrate_v2)


class TestMigrateV2(unittest.TestCase):
    """Test suite for V2 migration script"""

    def test_migrate_infrastructure_basic(self) -> None:
        """Test basic infrastructure migration"""
        db = {
            'domain_suffix': 'example.com',
            'letsencrypt': {'email': 'test@example.com'},
            'trusted_ips': ['192.168.1.1'],
            'traefik': {'version': 'v3'},
            'middleware': {'test': 'config'},
            'plugins': {'crowdsec': {'enabled': True}},
            'versions': {'traefik': 'v3'}
        }

        with patch.object(migrate_v2, 'replace_secrets_with_vars', side_effect=lambda x: x):
            result = migrate_v2.migrate_infrastructure(db)

        self.assertEqual(result['domain_suffix'], 'example.com')
        self.assertEqual(result['letsencrypt']['email'], 'test@example.com')
        self.assertEqual(result['trusted_ips'], ['192.168.1.1'])
        self.assertEqual(result['traefik']['version'], 'v3')
        self.assertEqual(result['middleware']['test'], 'config')
        self.assertEqual(result['plugins']['crowdsec']['enabled'], True)
        self.assertEqual(result['versions']['traefik'], 'v3')

    def test_migrate_infrastructure_partial(self) -> None:
        """Test infrastructure migration with only some fields"""
        db = {
            'domain_suffix': 'example.com',
            'traefik': {'version': 'v3'},
        }

        with patch.object(migrate_v2, 'replace_secrets_with_vars', side_effect=lambda x: x):
            result = migrate_v2.migrate_infrastructure(db)

        self.assertEqual(result['domain_suffix'], 'example.com')
        self.assertEqual(result['traefik']['version'], 'v3')
        self.assertNotIn('letsencrypt', result)
        self.assertNotIn('trusted_ips', result)

    def test_replace_secrets_with_vars_no_secrets_file(self) -> None:
        """Test secret replacement when secrets file doesn't exist"""
        data = {'key': 'value', 'nested': {'key2': 'value2'}}

        with patch('pathlib.Path.exists', return_value=False):
            result = migrate_v2.replace_secrets_with_vars(data)

        # Should return data unchanged if no secrets file
        self.assertEqual(result, data)

    def test_replace_secrets_with_vars_with_secrets(self) -> None:
        """Test secret replacement with actual secrets"""
        data = {
            'apikey': 'secret123',
            'nested': {
                'password': 'pass456',
                'other': 'normal'
            }
        }

        secrets_content = "API_KEY=secret123\nPASSWORD=pass456\n"

        with patch('pathlib.Path.exists', return_value=True):
            with patch('builtins.open', mock_open(read_data=secrets_content)):
                result = migrate_v2.replace_secrets_with_vars(data)

        self.assertEqual(result['apikey'], '${API_KEY}')
        self.assertEqual(result['nested']['password'], '${PASSWORD}')
        self.assertEqual(result['nested']['other'], 'normal')

    def test_replace_secrets_with_vars_list(self) -> None:
        """Test secret replacement in lists"""
        data = {
            'items': ['secret123', 'normal', 'pass456']
        }

        secrets_content = "API_KEY=secret123\nPASSWORD=pass456\n"

        with patch('pathlib.Path.exists', return_value=True):
            with patch('builtins.open', mock_open(read_data=secrets_content)):
                result = migrate_v2.replace_secrets_with_vars(data)

        self.assertEqual(result['items'][0], '${API_KEY}')
        self.assertEqual(result['items'][1], 'normal')
        self.assertEqual(result['items'][2], '${PASSWORD}')

    def test_replace_secrets_with_vars_io_error(self) -> None:
        """Test secret replacement handles IO errors gracefully"""
        data = {'key': 'value'}

        with patch('pathlib.Path.exists', return_value=True):
            with patch('builtins.open', side_effect=IOError("File read error")):
                # Should not raise, just continue without replacement
                result = migrate_v2.replace_secrets_with_vars(data)

        self.assertEqual(result, data)

    def test_migrate_project_basic(self) -> None:
        """Test basic project migration"""
        project = {
            'name': 'test-project',
            'enabled': True,
            'services': [
                {
                    'host': 'web',
                    'image': 'nginx:latest',
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
            compose, traefik = migrate_v2.migrate_project(project)

        # Check docker-compose structure
        self.assertIn('services', compose)
        self.assertIn('web', compose['services'])
        self.assertEqual(compose['services']['web']['image'], 'nginx:latest')
        self.assertEqual(compose['services']['web']['networks'], ['traefik'])

        # Check traefik structure
        self.assertEqual(traefik['enabled'], True)
        self.assertEqual(len(traefik['ingress']), 1)
        self.assertEqual(traefik['ingress'][0]['service'], 'web')
        self.assertEqual(traefik['ingress'][0]['domain'], 'example.com')
        self.assertEqual(traefik['ingress'][0]['port'], 80)

    def test_migrate_project_missing_name(self) -> None:
        """Test project migration fails gracefully without name"""
        project = {
            'services': []
        }

        with self.assertRaises(ValueError) as context:
            migrate_v2.migrate_project(project)

        self.assertIn("missing required 'name' field", str(context.exception))

    def test_migrate_project_missing_host(self) -> None:
        """Test project migration fails when service missing host"""
        project = {
            'name': 'test-project',
            'services': [
                {
                    'image': 'nginx:latest'
                    # Missing 'host'
                }
            ]
        }

        with self.assertRaises(ValueError) as context:
            migrate_v2.migrate_project(project)

        self.assertIn("missing required 'host' field", str(context.exception))

    def test_migrate_project_with_env(self) -> None:
        """Test project migration with environment variables"""
        project = {
            'name': 'test-project',
            'env': {
                'PROJECT_VAR': 'project_value'
            },
            'services': [
                {
                    'host': 'web',
                    'image': 'nginx:latest',
                    'env': {
                        'SERVICE_VAR': 'service_value'
                    }
                }
            ]
        }

        with patch.object(migrate_v2, 'replace_secrets_with_vars', side_effect=lambda x: x):
            compose, _ = migrate_v2.migrate_project(project)

        # Service should have both project and service env vars
        env = compose['services']['web']['environment']
        self.assertEqual(env['PROJECT_VAR'], 'project_value')
        self.assertEqual(env['SERVICE_VAR'], 'service_value')

    def test_migrate_project_with_volumes(self) -> None:
        """Test project migration with volumes"""
        project = {
            'name': 'test-project',
            'services': [
                {
                    'host': 'web',
                    'image': 'nginx:latest',
                    'volumes': ['/data:/data', '/config:/config']
                }
            ]
        }

        with patch.object(migrate_v2, 'replace_secrets_with_vars', side_effect=lambda x: x):
            compose, _ = migrate_v2.migrate_project(project)

        self.assertEqual(
            compose['services']['web']['volumes'],
            ['/data:/data', '/config:/config']
        )

    def test_migrate_project_with_additional_properties(self) -> None:
        """Test project migration with additional docker compose properties"""
        project = {
            'name': 'test-project',
            'services': [
                {
                    'host': 'web',
                    'image': 'nginx:latest',
                    'additional_properties': {
                        'cap_add': ['NET_ADMIN'],
                        'privileged': True
                    }
                }
            ]
        }

        with patch.object(migrate_v2, 'replace_secrets_with_vars', side_effect=lambda x: x):
            compose, _ = migrate_v2.migrate_project(project)

        self.assertEqual(compose['services']['web']['cap_add'], ['NET_ADMIN'])
        self.assertTrue(compose['services']['web']['privileged'])

    def test_migrate_project_ingress_tls_sans(self) -> None:
        """Test project migration with TLS SANs in ingress"""
        project = {
            'name': 'test-project',
            'services': [
                {
                    'host': 'web',
                    'image': 'nginx:latest',
                    'ingress': [
                        {
                            'domain': 'example.com',
                            'port': 443,
                            'tls': {
                                'sans': ['www.example.com', 'api.example.com']
                            }
                        }
                    ]
                }
            ]
        }

        with patch.object(migrate_v2, 'replace_secrets_with_vars', side_effect=lambda x: x):
            _, traefik = migrate_v2.migrate_project(project)

        self.assertEqual(
            traefik['ingress'][0]['tls_sans'],
            ['www.example.com', 'api.example.com']
        )

    def test_validate_project_name_valid(self) -> None:
        """Test valid project names"""
        valid_names = ['test-project', 'my_project', 'project123', 'ProjectName']
        for name in valid_names:
            self.assertEqual(migrate_v2.validate_project_name(name), name)

    def test_validate_project_name_path_traversal(self) -> None:
        """Test project name validation prevents path traversal"""
        invalid_names = [
            '../../../etc',
            './project',
            'project/../other',
            '/absolute/path',
            'project/subdir'
        ]

        for name in invalid_names:
            with self.assertRaises(ValueError) as context:
                migrate_v2.validate_project_name(name)
            self.assertIn('Invalid project name', str(context.exception))

    def test_validate_project_name_special_dirs(self) -> None:
        """Test project name validation rejects special directory names"""
        invalid_names = ['.', '..', '']

        for name in invalid_names:
            with self.assertRaises(ValueError):
                migrate_v2.validate_project_name(name)

    def test_check_file_exists_no_file(self) -> None:
        """Test check_file_exists when file doesn't exist"""
        path = Path('/nonexistent/file.yml')

        with patch.object(Path, 'exists', return_value=False):
            result = migrate_v2.check_file_exists(path, force=False)

        self.assertTrue(result)

    def test_check_file_exists_with_force(self) -> None:
        """Test check_file_exists with force flag"""
        path = Path('/existing/file.yml')

        with patch.object(Path, 'exists', return_value=True):
            result = migrate_v2.check_file_exists(path, force=True)

        self.assertTrue(result)

    def test_check_file_exists_without_force(self) -> None:
        """Test check_file_exists rejects existing file without force"""
        path = Path('/existing/file.yml')

        with patch.object(Path, 'exists', return_value=True):
            result = migrate_v2.check_file_exists(path, force=False)

        self.assertFalse(result)

    @patch('migrate_v2.validate_db')
    @patch('migrate_v2.Path')
    @patch('builtins.open', new_callable=mock_open)
    @patch('migrate_v2.logger')
    def test_main_dry_run(
        self,
        mock_logger: Mock,
        mock_file: Mock,
        mock_path: Mock,
        mock_validate: Mock
    ) -> None:
        """Test main function in dry-run mode"""
        test_db = {
            'projects': [
                {'name': 'project1'},
                {'name': 'project2'}
            ]
        }

        # Setup mocks
        mock_path.return_value.exists.return_value = True
        mock_file.return_value.read.return_value = yaml.dump(test_db)

        with patch('sys.argv', ['migrate-v2.py', '--dry-run']):
            with patch('yaml.safe_load', return_value=test_db):
                result = migrate_v2.main()

        self.assertEqual(result, 0)
        # Should not write any files in dry-run mode
        mock_file.return_value.write.assert_not_called()

    @patch('migrate_v2.validate_db')
    @patch('builtins.open', new_callable=mock_open)
    @patch('migrate_v2.logger')
    def test_main_db_not_found(
        self,
        mock_logger: Mock,
        mock_file: Mock,
        mock_validate: Mock
    ) -> None:
        """Test main function when db.yml doesn't exist"""
        with patch('sys.argv', ['migrate-v2.py']):
            with patch('pathlib.Path.exists', return_value=False):
                result = migrate_v2.main()

        self.assertEqual(result, 1)

    @patch('migrate_v2.validate_db', side_effect=Exception("Validation error"))
    @patch('builtins.open', new_callable=mock_open)
    @patch('migrate_v2.logger')
    def test_main_validation_fails(
        self,
        mock_logger: Mock,
        mock_file: Mock,
        mock_validate: Mock
    ) -> None:
        """Test main function when validation fails"""
        with patch('sys.argv', ['migrate-v2.py']):
            with patch('pathlib.Path.exists', return_value=True):
                result = migrate_v2.main()

        self.assertEqual(result, 1)

    @patch('migrate_v2.validate_db')
    @patch('builtins.open', new_callable=mock_open, read_data="invalid: yaml: data: [")
    @patch('migrate_v2.logger')
    def test_main_invalid_yaml(
        self,
        mock_logger: Mock,
        mock_file: Mock,
        mock_validate: Mock
    ) -> None:
        """Test main function with invalid YAML"""
        with patch('sys.argv', ['migrate-v2.py']):
            with patch('pathlib.Path.exists', return_value=True):
                with patch('yaml.safe_load', side_effect=yaml.YAMLError("Invalid YAML")):
                    result = migrate_v2.main()

        self.assertEqual(result, 1)


if __name__ == '__main__':
    unittest.main()
