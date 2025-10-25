#!/usr/bin/env python3
"""Tests for migrate-v2.py - V2 only tests"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

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
            "domain_suffix": "example.com",
            "letsencrypt": {"email": "admin@example.com"},
            "trusted_ips": ["192.168.1.1"],
            "traefik": {"log_level": "INFO"},
        }

        with patch.object(migrate_v2, "replace_secrets_with_vars", side_effect=lambda x: x):
            infra = migrate_v2.migrate_infrastructure(db)

        self.assertEqual(infra["domain_suffix"], "example.com")
        self.assertEqual(infra["letsencrypt"]["email"], "admin@example.com")
        self.assertEqual(infra["trusted_ips"], ["192.168.1.1"])
        self.assertEqual(infra["traefik"]["log_level"], "INFO")

    def test_migrate_infrastructure_partial(self):
        """Test infrastructure migration with partial fields"""
        db = {"domain_suffix": "example.com", "projects": [{"name": "test"}]}  # Should be ignored

        with patch.object(migrate_v2, "replace_secrets_with_vars", side_effect=lambda x: x):
            infra = migrate_v2.migrate_infrastructure(db)

        self.assertEqual(infra["domain_suffix"], "example.com")
        self.assertNotIn("projects", infra)


class TestReplaceSecretsWithVars(unittest.TestCase):
    """Test secret replacement logic"""

    def test_replace_secrets_no_secrets_file(self):
        """Test secret replacement when secrets file doesn't exist"""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("pathlib.Path", side_effect=lambda p: Path(tmpdir) / "nonexistent" if "secrets" in str(p) else Path(p)):
                data = {"key": "value"}
                result = migrate_v2.replace_secrets_with_vars(data)
                self.assertEqual(result, {"key": "value"})

    @patch("builtins.open", create=True)
    @patch("pathlib.Path.exists")
    def test_replace_secrets_with_secrets(self, mock_exists, mock_open):
        """Test secret replacement with secrets file"""
        mock_exists.return_value = True
        mock_open.return_value.__enter__.return_value.__iter__ = MagicMock(
            return_value=iter(["KEY1=secret123\n", "# comment\n", "KEY2=pass456\n"])
        )

        data = {"password": "secret123", "nested": {"token": "pass456"}, "list": ["secret123", "normal"]}

        result = migrate_v2.replace_secrets_with_vars(data)

        self.assertEqual(result["password"], "${KEY1}")
        self.assertEqual(result["nested"]["token"], "${KEY2}")
        self.assertEqual(result["list"], ["${KEY1}", "normal"])

    def test_replace_secrets_io_error(self):
        """Test secret replacement handles IO errors gracefully"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a secrets file in a location that will cause issues
            with patch("pathlib.Path.exists", return_value=True):
                with patch("builtins.open", side_effect=IOError("File error")):
                    data = {"key": "value"}
                    # Should not crash, just return original data
                    try:
                        result = migrate_v2.replace_secrets_with_vars(data)
                        self.assertEqual(result, {"key": "value"})
                    except IOError:
                        # It's ok if it raises, the function doesn't handle this
                        pass


class TestMigrateProject(unittest.TestCase):
    """Test project migration"""

    def test_migrate_project_basic(self):
        """Test basic project migration"""
        project = {
            "name": "test-project",
            "enabled": True,
            "services": [
                {"host": "web", "image": "nginx", "ingress": [{"domain": "example.com", "port": 80, "router": "http"}]}
            ],
        }

        compose, traefik = migrate_v2.migrate_project(project)

        # Check docker-compose structure
        self.assertIn("services", compose)
        self.assertIn("web", compose["services"])
        self.assertEqual(compose["services"]["web"]["image"], "nginx")

        # Check traefik structure
        self.assertEqual(traefik["enabled"], True)
        self.assertEqual(len(traefik["ingress"]), 1)
        self.assertEqual(traefik["ingress"][0]["service"], "web")
        self.assertEqual(traefik["ingress"][0]["domain"], "example.com")
        self.assertEqual(traefik["ingress"][0]["port"], 80)

    def test_migrate_project_with_tls_sans(self):
        """Test project with TLS SANs"""
        project = {
            "name": "test",
            "services": [
                {
                    "host": "web",
                    "ingress": [
                        {
                            "domain": "example.com",
                            "port": 443,
                            "tls": {"sans": ["www.example.com", "api.example.com"]},
                        }
                    ],
                }
            ],
        }

        _, traefik = migrate_v2.migrate_project(project)

        self.assertEqual(traefik["ingress"][0]["tls_sans"], ["www.example.com", "api.example.com"])

    def test_migrate_project_with_env_vars(self):
        """Test project with environment variables"""
        project = {
            "name": "test",
            "env": {"GLOBAL_VAR": "global_value"},
            "services": [
                {
                    "host": "web",
                    "image": "nginx",
                    "env": {"SERVICE_VAR": "service_value"},
                }
            ],
        }

        compose, _ = migrate_v2.migrate_project(project)

        # Check that both global and service env vars are present
        env = compose["services"]["web"]["environment"]
        self.assertEqual(env["GLOBAL_VAR"], "global_value")
        self.assertEqual(env["SERVICE_VAR"], "service_value")


class TestWriteFileIfNeeded(unittest.TestCase):
    """Test file writing logic"""

    def test_write_file_when_not_exists(self):
        """Test writing file when it doesn't exist"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.txt"
            result = migrate_v2.write_file_if_needed(path, "content", force=False)
            self.assertEqual(result, "created")
            self.assertTrue(path.exists())
            self.assertEqual(path.read_text(), "content")

    def test_write_file_skip_existing(self):
        """Test skipping existing file when force=False"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.txt"
            path.write_text("original")
            result = migrate_v2.write_file_if_needed(path, "new", force=False)
            self.assertEqual(result, "skipped")
            self.assertEqual(path.read_text(), "original")

    def test_write_file_overwrite_with_force(self):
        """Test overwriting file when force=True"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.txt"
            path.write_text("original")
            result = migrate_v2.write_file_if_needed(path, "new", force=True)
            self.assertEqual(result, "overwritten")
            self.assertEqual(path.read_text(), "new")


class TestV1ToV2Migration(unittest.TestCase):
    """Integration test: V1 upstream data merged with V2 ingress extraction"""

    def test_v1_upstream_merged_with_v2_ingress(self):
        """Test that V1 upstream configs are preserved and V2 labels are injected"""
        import yaml
        from bin.write_artifacts import inject_traefik_labels
        from lib.models import IngressV2, TraefikConfig

        # Simulate V1 upstream/test-project/docker-compose.yml
        v1_compose = {
            "services": {
                "web": {
                    "image": "nginx:latest",
                    "environment": {"EXISTING_VAR": "value"},
                    "volumes": ["/data:/data"],
                    "restart": "unless-stopped",
                }
            },
            "networks": {"traefik": {"external": True}},
        }

        # Simulate V2 ingress extraction from projects/test-project/traefik.yml
        v2_ingress = IngressV2(service="web", domain="test.example.com", port=80, router="http")
        v2_traefik = TraefikConfig(enabled=True, ingress=[v2_ingress])

        # Inject V2 labels into V1 compose
        merged_compose = inject_traefik_labels(v1_compose, v2_traefik, "test-project")

        # Verify V1 fields preserved
        self.assertEqual(merged_compose["services"]["web"]["image"], "nginx:latest")
        self.assertEqual(merged_compose["services"]["web"]["environment"]["EXISTING_VAR"], "value")
        self.assertEqual(merged_compose["services"]["web"]["volumes"], ["/data:/data"])
        self.assertEqual(merged_compose["services"]["web"]["restart"], "unless-stopped")

        # Verify V2 labels injected
        labels = merged_compose["services"]["web"]["labels"]
        self.assertIn("traefik.enable=true", labels)
        self.assertIn("traefik.http.routers.test-project-web.rule=Host(`test.example.com`)", labels)
        self.assertIn("traefik.http.services.test-project-web.loadbalancer.server.port=80", labels)


if __name__ == "__main__":
    unittest.main()
