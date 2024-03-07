import os
import sys
import unittest
from unittest import TestCase, mock
from unittest.mock import Mock, call

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from lib.data import Service
from lib.models import Project
from lib.proxy import (
    get_internal_map,
    get_passthrough_map,
    get_terminate_map,
    reload_proxy,
    write_maps,
    write_proxies,
    write_proxy,
    write_terminate,
)
from lib.test_stubs import test_db


class TestProxy(TestCase):
    @mock.patch("lib.proxy.get_domains")
    def test_get_internal_map(self, mock_get_domains: Mock) -> None:
        # Mock the get_domains function
        mock_get_domains.return_value = ["example.com", "example.org"]

        # Call the function under test
        internal_map = get_internal_map()

        # Assert the result
        expected_map = {
            "example.com": "terminate:8443",
            "example.org": "terminate:8443",
        }
        self.assertEqual(internal_map, expected_map)

    @mock.patch(
        "lib.data.get_db",
        return_value=test_db,
    )
    def test_get_terminate_map(self, _: Mock) -> None:

        # Call the function under test
        terminate_map = get_terminate_map()

        # Assert the result
        expected_map = {
            "itsup.example.com": "host.docker.internal:8888",
            "hello.example.com": "test-master:8080",
            "whoami.example.com": "whoami-web:8080",
        }
        self.assertEqual(terminate_map, expected_map)

    @mock.patch(
        "lib.proxy.get_projects",
        return_value=[
            Project(
                name="testp",
                domain="example.com",
                entrypoint="bla",
                services=[
                    Service(name="my_service", port=8080, passthrough=True),
                ],
            ),
        ],
    )
    def test_get_passthrough_map(self, _: Mock) -> None:

        # Call the function under test
        passthrough_map = get_passthrough_map()

        # Assert the result
        expected_map = {
            "example.com": "my_service:8080",
        }
        self.assertEqual(passthrough_map, expected_map)

    @mock.patch("builtins.open", new_callable=mock.mock_open)
    @mock.patch("jinja2.Template")
    @mock.patch("lib.proxy.get_internal_map")
    @mock.patch("lib.proxy.get_passthrough_map")
    @mock.patch("lib.proxy.get_terminate_map")
    def test_write_maps(
        self,
        mock_get_terminate_map: Mock,
        mock_get_passthrough_map: Mock,
        mock_get_internal_map: Mock,
        mock_template: Mock,
        mock_open: Mock,
    ) -> None:
        # Mock the get_internal_map function
        mock_get_internal_map.return_value = {
            "example.com": "terminate:8080",
            "example.org": "terminate:8080",
        }

        # Mock the get_passthrough_map function
        mock_get_passthrough_map.return_value = {
            "example.com": "my_service:8080",
            "example.org": "my_service:8080",
        }

        # Mock the get_terminate_map function
        mock_get_terminate_map.return_value = {
            "example.com": "my_project-my_service:8080",
            "example.org": "my_service:8080",
        }

        mock_template.return_value = {"render": Mock()}

        # Call the function under test
        write_maps()

        self.assertEqual(
            mock_open.call_args_list,
            [
                mock.call("proxy/tpl/map.conf.j2", encoding="utf-8"),
                mock.call("proxy/nginx/map/internal.conf", "w", encoding="utf-8"),
                mock.call("proxy/nginx/map/passthrough.conf", "w", encoding="utf-8"),
                mock.call("proxy/nginx/map/terminate.conf", "w", encoding="utf-8"),
            ],
        )

    @mock.patch("builtins.open", new_callable=mock.mock_open)
    @mock.patch("lib.proxy.get_project")
    def test_write_proxy(self, _: Mock, mock_open: Mock) -> None:

        # Call the function under test
        write_proxy()

        # Assert that 'open' is called twice with the correct arguments
        self.assertEqual(
            mock_open.call_args_list,
            [
                call("proxy/tpl/proxy.conf.j2", encoding="utf-8"),
                call("proxy/nginx/proxy.conf", "w", encoding="utf-8"),
            ],
        )

    @mock.patch("builtins.open", new_callable=mock.mock_open)
    @mock.patch("lib.proxy.get_domains")
    @mock.patch("lib.proxy.get_project")
    def test_write_terminate(self, _: Mock, mock_get_domains: Mock, mock_open: Mock) -> None:
        mock_get_domains.return_value = ["example.com", "example.org"]

        # Call the function under test
        write_terminate()

        # Assert that 'open' is called twice with the correct arguments
        self.assertEqual(
            mock_open.call_args_list,
            [
                call("proxy/tpl/terminate.conf.j2", encoding="utf-8"),
                call("proxy/nginx/terminate.conf", "w", encoding="utf-8"),
            ],
        )

    @mock.patch(
        "os.environ", return_value={"TRAEFIK_DOMAIN": "traefik.example.com", "TRUSTED_IPS_CIDRS": "192.168.1.1"}
    )
    @mock.patch("lib.proxy.write_maps")
    @mock.patch("lib.proxy.write_proxy")
    @mock.patch("lib.proxy.write_terminate")
    @mock.patch("lib.proxy.write_compose")
    @mock.patch("lib.proxy.write_config")
    @mock.patch("lib.proxy.write_routers")
    def test_write_proxies(
        self,
        mock_write_routers: Mock,
        mock_write_config: Mock,
        mock_write_compose: Mock,
        mock_write_terminate: Mock,
        mock_write_proxy: Mock,
        mock_write_maps: Mock,
        _: Mock,
    ) -> None:
        # Call the function under test
        write_proxies()

        # Assert that the write_maps, write_proxy, and write_terminate functions are called
        mock_write_maps.assert_called_once()
        mock_write_proxy.assert_called_once()
        mock_write_terminate.assert_called_once()
        mock_write_compose.assert_called_once()
        mock_write_config.assert_called_once()
        mock_write_routers.assert_called_once()

    @mock.patch("lib.proxy.run_command")
    def test_reload_proxy(self, mock_run_command: Mock) -> None:

        # Call the function under test
        reload_proxy()

        # Assert that the subprocess.Popen was called twice
        mock_run_command.assert_has_calls(
            [
                call(
                    ["docker", "compose", "exec", "proxy", "nginx", "-s", "reload"],
                    cwd="proxy",
                ),
                call(
                    ["docker", "compose", "exec", "terminate", "nginx", "-s", "reload"],
                    cwd="proxy",
                ),
            ]
        )

    @mock.patch("lib.proxy.run_command")
    def test_reload_proxy_with_service(self, mock_run_command: Mock) -> None:

        # Call the function under test
        reload_proxy(service="terminate")

        # Assert that the subprocess.Popen was called with the correct arguments
        mock_run_command.assert_called_once_with(
            ["docker", "compose", "exec", "terminate", "nginx", "-s", "reload"],
            cwd="proxy",
        )


if __name__ == "__main__":
    unittest.main()
