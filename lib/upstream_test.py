import unittest
from unittest import TestCase, mock
from unittest.mock import Mock, call

from lib.models import (  # Import necessary models
    TLS,
    Env,
    Ingress,
    Project,
    Protocol,
    ProxyProtocol,
    Router,
    Service,
)
from lib.upstream import (
    check_upstream,
    rollout_service,
    update_upstream,
    update_upstreams,
    write_upstream,
    write_upstream_volume_folders,
    write_upstreams,
)


class DirEntry:
    def __init__(self, path: str):
        self.path = path

    def is_dir(self) -> bool:
        return True


_ret_tpl = """
---
version: '3.8'

networks:
  proxynet:
    name: proxynet
    external: true

services:

  test-master:
    image: morriz/hello-world:main
    command: ["/app/run", "--verbose"] # Added command
    depends_on:                        # Added depends_on
      - test-informant
    networks:
      - default
      - proxynet
    restart: unless-stopped
    environment:
      TARGET: cost concerned people
      INFORMANT: http://test-informant:8080
      
    expose:
      - '8080'
    
    volumes:
      - ./data/bla:/data/bla
      - ./etc/dida:/etc/dida
      
    labels:                            # Added labels
      - "traefik.enable=true"
      - "traefik.http.routers.test-master.rule=Host(`master.example.com`)"
      - "traefik.http.services.test-master.loadbalancer.server.port=8080"
      - "my.custom.label=value1"
    extra_key: extra_value             # Added for additional_properties

  test-informant:
    image: morriz/hello-world:main
    networks:
      - default
      - proxynet
    restart: unless-stopped
    environment:
      TARGET: boss
      
    expose:
      - '8080'"""

_ret_projects = [
    Project(  # Updated Project 1: Comprehensive Example
        name="comprehensive-project",
        description="A project demonstrating various features",
        enabled=True,
        env=Env(**{"PROJECT_LEVEL_VAR": "project_value"}),  # Project-level env
        services=[
            Service(
                host="app-main",
                image="minio/minio:latest",
                command='server --console-address ":9001" /data',
                env=Env(**{"MINIO_ROOT_USER": "root", "MINIO_ROOT_PASSWORD": "password"}),
                volumes=["/data", "config:/etc/minio/config"],  # Host and named volume
                restart="always",
                depends_on=["db-service"],  # Example depends_on list
                labels=["traefik.http.middlewares.test-auth.basicauth.users=test:test"],  # Example label
                additional_properties={
                    "cap_add": ["NET_ADMIN"],
                    "ulimits": {"nofile": {"soft": 65535, "hard": 65535}},
                },  # Example additional_properties
                ingress=[
                    Ingress(
                        domain="minio-api.example.com", port=9000, router=Router.tcp, proxyprotocol=None
                    ),  # TCP ingress, no proxy proto
                    Ingress(domain="minio-ui.example.com", port=9001, router=Router.http),  # HTTP ingress (default)
                    Ingress(
                        domain="minio-alt.example.com",
                        port=9002,
                        router=Router.http,
                        path_prefix="/alt",
                        path_remove=True,
                    ),  # Path prefix/remove
                    Ingress(port=9003, expose=True),  # Internal expose only
                    Ingress(
                        tls=TLS(main="secure.example.com", sans=["secure-alt.example.com"]), port=9443
                    ),  # Custom TLS
                    Ingress(
                        domain="proxyproto.example.com", port=9004, proxyprotocol=ProxyProtocol.v1
                    ),  # Explicit Proxy Protocol v1
                ],
            ),
            Service(
                host="172.17.0.1",  # IP host
                image="traefik/whoami:latest",
                ingress=[Ingress(domain="whoami.example.com", port=80)],  # Simple ingress
            ),
            Service(  # Service for depends_on target
                host="db-service",
                image="postgres:latest",
                env=Env(**{"POSTGRES_PASSWORD": "password"}),
                volumes=["db_data:/var/lib/postgresql/data"],  # Named volume only
                depends_on={"other-service": {"condition": "service_healthy"}},  # Example depends_on dict
            ),
            Service(  # Service for depends_on target dict
                host="other-service",
                image="some-healthcheck-image:latest",
            ),
        ],
    ),
    Project(  # Updated Project 2: Passthrough and UDP Example
        name="passthrough-project",
        description="A project demonstrating passthrough and UDP",
        enabled=False,
        services=[
            Service(
                host="192.168.1.111",  # IP host
                # No image needed for pure passthrough? Assuming upstream handles it.
                ingress=[
                    Ingress(
                        domain="home.example.com", passthrough=True, port=443, router=Router.tcp
                    ),  # TCP passthrough
                    Ingress(
                        domain="home.example.com",
                        passthrough=True,
                        path_prefix="/.well-known/acme-challenge/",
                        port=80,
                        router=Router.http,
                    ),  # ACME challenge passthrough
                ],
            ),
            Service(
                host="vpn-server",  # Service name host
                image="nubacuk/docker-openvpn:latest",
                volumes=["/etc/openvpn"],  # Host path volume
                additional_properties={"cap_add": ["NET_ADMIN"]},
                restart="unless-stopped",  # Default restart
                ingress=[
                    Ingress(
                        domain="vpn.example.com", hostport=1194, port=1194, protocol=Protocol.udp, router=Router.udp
                    ),  # UDP ingress with hostport
                ],
            ),
        ],
    ),
]


class TestUpdateUpstream(TestCase):
    @mock.patch("builtins.open", new_callable=mock.mock_open, read_data=_ret_tpl)
    def test_write_upstream(
        self,
        mock_open: Mock,
    ) -> None:

        project = Project(
            name="test",
            services=[
                Service(
                    image="morriz/hello-world:main",
                    host="master",
                    # port=8080, # Port is mainly for ingress/expose logic
                    command="/app/run --verbose",  # Added
                    depends_on=["test-informant"],  # Added
                    env=Env(**{"TARGET": "cost concerned people", "INFORMANT": "http://test-informant:8080"}),
                    volumes=["./data/bla:/data/bla", "./etc/dida:/etc/dida"],
                    labels=["my.custom.label=value1"],  # Added
                    additional_properties={"extra_key": "extra_value"},  # Added
                    ingress=[  # Added ingress example to generate labels
                        Ingress(domain="master.example.com", port=8080)
                    ],
                ),
                Service(image="morriz/hello-world:main", host="informant", port=8080, env=Env(**{"TARGET": "boss"})),
            ],
        )

        # Call the function under test
        write_upstream(project)

        # Assert that the subprocess.Popen was called with the correct arguments
        mock_open.return_value.write.assert_called_once_with(_ret_tpl)

    @mock.patch("lib.upstream.rollout_service")
    @mock.patch("lib.upstream.run_command")
    @mock.patch(
        "lib.upstream.get_projects",
        return_value=[_ret_projects[0]],
    )
    @mock.patch("lib.upstream.get_project", return_value=_ret_projects[0])
    def test_update_upstream_enabled(
        self,
        _: Mock,
        _2: Mock,
        mock_run_command: Mock,
        mock_rollout_service: Mock,
    ) -> None:

        # Use names from the updated _ret_projects[0]
        project_name = "comprehensive-project"
        service_name = "app-main"

        # Call the function under test
        update_upstream(
            project_name,
            service_name,
        )

        # Assert that the subprocess.Popen was called with the correct arguments
        mock_run_command.assert_has_calls(
            [
                call(
                    ["docker", "compose", "pull"],
                    cwd=f"upstream/{project_name}",
                ),
                call(
                    ["docker", "compose", "up", "-d"],
                    cwd=f"upstream/{project_name}",
                ),
            ]
        )

        # Assert that the rollout_service function is called correctly
        # with the correct arguments
        mock_rollout_service.assert_called_once_with(project_name, service_name)

    @mock.patch("lib.upstream.rollout_service")
    @mock.patch("lib.upstream.run_command")
    @mock.patch(
        "lib.upstream.get_projects",
        # Return a project with multiple services for this test
        return_value=[
            Project(
                name="my-project-multi",
                enabled=True,
                services=[
                    Service(host="service1", image="img1"),
                    Service(host="service2", image="img2"),
                ],
            )
        ],
    )
    @mock.patch(
        "lib.upstream.get_project",
        return_value=Project(
            name="my-project-multi",
            enabled=True,
            services=[Service(host="service1", image="img1"), Service(host="service2", image="img2")],
        ),
    )
    def test_update_upstream_rollout_all_services(
        self,
        _: Mock,
        _2: Mock,
        _3: Mock,  # mock_run_command (unused in assertion)
        mock_rollout_service: Mock,
    ) -> None:
        # Call the function under test with service=None
        update_upstream(
            "my-project-multi",
            service=None,  # Explicitly None
        )

        # Assert that rollout_service is called for each service
        mock_rollout_service.assert_has_calls(
            [
                call("my-project-multi", "service1"),
                call("my-project-multi", "service2"),
            ],
            any_order=True,
        )

    @mock.patch("lib.upstream.rollout_service")
    @mock.patch("lib.upstream.run_command")
    @mock.patch(
        "lib.upstream.get_projects",
        return_value=[],
    )
    @mock.patch("lib.upstream.get_project", return_value=_ret_projects[1])
    def test_update_upstream_disabled(
        self,
        _: Mock,
        _2: Mock,
        mock_run_command: Mock,
        mock_rollout_service: Mock,
    ) -> None:

        # Use names from the updated _ret_projects[1]
        project_name = "passthrough-project"
        service_name = "vpn-server"  # Use one of the services in this project

        # Call the function under test
        update_upstream(
            project_name,
            service_name,  # Service name doesn't strictly matter for down command, but use a valid one
        )

        # Assert that the subprocess.Popen was called with the correct arguments
        mock_run_command.assert_has_calls(
            [
                call(
                    ["docker", "compose", "down"],
                    cwd=f"upstream/{project_name}",
                ),
            ]
        )

        # Assert that the rollout_service function is called correctly
        # with the correct arguments
        mock_rollout_service.assert_not_called()

    @mock.patch("os.scandir")
    @mock.patch("lib.upstream.update_upstream")
    @mock.patch("lib.upstream.run_command")
    @mock.patch("lib.upstream.get_project", return_value=_ret_projects[0])
    def test_update_upstreams(self, _: Mock, _2: Mock, mock_update_upstream: Mock, mock_scandir: Mock) -> None:
        # Use name from the updated _ret_projects[0]
        project_name = "comprehensive-project"
        mock_scandir.return_value = [DirEntry(f"upstream/{project_name}")]

        # Call the function under test
        update_upstreams()

        mock_update_upstream.assert_called_once_with(
            project_name,
        )


# New Test Class for write_upstream_volume_folders
class TestWriteUpstreamVolumeFolders(TestCase):
    @mock.patch("os.makedirs")
    def test_write_upstream_volume_folders_simple(self, mock_makedirs: Mock) -> None:
        project = Project(
            name="test-simple",
            services=[
                Service(host="s1", volumes=["data:/data", "config:/config"]),
                Service(host="s2", volumes=["./logs:/app/logs"]),  # Relative path
            ],
        )
        write_upstream_volume_folders(project)
        mock_makedirs.assert_has_calls(
            [
                call("upstream/test-simple/data", exist_ok=True),
                call("upstream/test-simple/config", exist_ok=True),
                call("upstream/test-simple/logs", exist_ok=True),
            ],
            any_order=True,
        )

    @mock.patch("os.makedirs")
    def test_write_upstream_volume_folders_complex(self, mock_makedirs: Mock) -> None:
        project = Project(
            name="test-complex",
            services=[
                Service(host="s1", volumes=["/host/path:/container/path", "../relative/host:/container/relative"]),
                Service(host="s2", volumes=["data:/data:ro", "config:/config:rw"]),  # With options
                Service(host="s3", volumes=["namedvolume"]),
            ],
        )
        write_upstream_volume_folders(project)
        # Only non-host paths should trigger makedirs
        mock_makedirs.assert_has_calls(
            [
                call("upstream/test-complex/data", exist_ok=True),
                call("upstream/test-complex/config", exist_ok=True),
                call("upstream/test-complex/namedvolume", exist_ok=True),
            ],
            any_order=True,
        )
        # Assert host paths were skipped
        self.assertEqual(mock_makedirs.call_count, 3)


# New Test Class for write_upstreams
class TestWriteUpstreams(TestCase):
    @mock.patch("lib.upstream.write_upstream_volume_folders")
    @mock.patch("lib.upstream.write_upstream")
    @mock.patch("os.makedirs")
    @mock.patch("lib.upstream.get_projects")
    def test_write_upstreams(
        self,
        mock_get_projects: Mock,
        mock_makedirs: Mock,
        mock_write_upstream: Mock,
        mock_write_volume_folders: Mock,
    ) -> None:
        # Added host field to satisfy Service model validation
        project1 = Project(name="proj1", enabled=True, services=[Service(host="s1", image="img1")])
        project2 = Project(name="proj2", enabled=True, services=[Service(host="s2", image="img2")])
        mock_get_projects.return_value = [project1, project2]

        write_upstreams()

        mock_get_projects.assert_called_once()
        self.assertTrue(callable(mock_get_projects.call_args[1]["filter"]))  # Check filter exists

        mock_makedirs.assert_has_calls(
            [
                call("upstream/proj1", exist_ok=True),
                call("upstream/proj2", exist_ok=True),
            ],
            any_order=True,
        )
        mock_write_upstream.assert_has_calls([call(project1), call(project2)], any_order=True)
        mock_write_volume_folders.assert_has_calls([call(project1), call(project2)], any_order=True)


# New Test Class for check_upstream
class TestCheckUpstream(TestCase):
    @mock.patch("lib.upstream.get_service")
    @mock.patch("lib.upstream.get_project")
    def test_check_upstream_project_only_exists(self, mock_get_project: Mock, mock_get_service: Mock) -> None:
        mock_get_project.return_value = Project(name="exists")
        try:
            check_upstream("exists")
        except ValueError:
            self.fail("check_upstream raised ValueError unexpectedly")
        mock_get_project.assert_called_once_with("exists")
        mock_get_service.assert_not_called()

    @mock.patch("lib.upstream.get_service")
    @mock.patch("lib.upstream.get_project")
    def test_check_upstream_project_and_service_exist(self, mock_get_project: Mock, mock_get_service: Mock) -> None:
        mock_get_project.return_value = Project(name="exists")
        mock_get_service.return_value = Service(host="service_exists")
        try:
            check_upstream("exists", "service_exists")
        except ValueError:
            self.fail("check_upstream raised ValueError unexpectedly")
        mock_get_project.assert_called_once_with("exists")
        mock_get_service.assert_called_once_with("exists", "service_exists")

    @mock.patch("lib.upstream.get_service")
    @mock.patch("lib.upstream.get_project", return_value=None)
    def test_check_upstream_project_does_not_exist(self, mock_get_project: Mock, mock_get_service: Mock) -> None:
        with self.assertRaisesRegex(ValueError, "Project notfound does not exist"):
            check_upstream("notfound")
        mock_get_project.assert_called_once_with("notfound")
        mock_get_service.assert_not_called()

    @mock.patch("lib.upstream.get_service", return_value=None)
    @mock.patch("lib.upstream.get_project")
    def test_check_upstream_service_does_not_exist(self, mock_get_project: Mock, mock_get_service: Mock) -> None:
        mock_get_project.return_value = Project(name="exists")
        with self.assertRaisesRegex(ValueError, "Project exists does not have service notfound"):
            check_upstream("exists", "notfound")
        mock_get_project.assert_called_once_with("exists")
        mock_get_service.assert_called_once_with("exists", "notfound")


# New Test Class for rollout_service
class TestRolloutService(TestCase):
    @mock.patch("lib.upstream.run_command")
    def test_rollout_service(self, mock_run_command: Mock) -> None:
        rollout_service("my-proj", "my-svc")
        mock_run_command.assert_called_once_with(["docker", "rollout", "my-proj-my-svc"], cwd="upstream/my-proj")


if __name__ == "__main__":
    unittest.main()
