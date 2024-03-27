import yaml

from lib.models import Ingress, Plugin, Project, Service

with open("db.yml.sample", encoding="utf-8") as f:
    test_db = yaml.safe_load(f)

test_plugins = {
    "crowdsec": Plugin(
        **{
            "enabled": False,
            "version": "v1.2.0",
            "options": {
                "logLevel": "INFO",
                "updateIntervalSeconds": 60,
                "defaultDecisionSeconds": 60,
                "httpTimeoutSeconds": 10,
                "crowdsecCapiMachineId": "login",
                "crowdsecCapiPassword": "password",
                "crowdsecCapiScenarios": [
                    "crowdsecurity/http-path-traversal-probing",
                    "crowdsecurity/http-xss-probing",
                    "crowdsecurity/http-generic-bf",
                ],
            },
        }
    )
}

test_projects = [
    Project(
        description="Home Assistant passthrough",
        enabled=False,
        name="home-assistant",
        services=[
            Service(ingress=[Ingress(domain="home.example.com", passthrough=True, port=443)], name="192.168.1.111"),
        ],
    ),
    Project(
        description="itsUP API running on the host",
        name="itsUP",
        services=[
            Service(ingress=[Ingress(domain="itsup.example.com", port=8888)], name="host.docker.internal"),
        ],
    ),
    Project(
        description="Minio service",
        enabled=False,
        name="minio",
        services=[
            Service(
                command='server --console-address ":9001" http://minio/data',
                env={
                    "MINIO_ROOT_USER": "root",
                    "MINIO_ROOT_PASSWORD": "83b01a6b8f210b5f5862943f3ebe257d",
                },
                image="minio/minio:latest",
                ingress=[
                    Ingress(domain="minio-api.example.com", port=9000),
                    Ingress(domain="minio-ui.example.com", port=9001),
                ],
                name="app",
                volumes=["/data"],
            ),
        ],
    ),
    Project(
        description="VPN server",
        enabled=False,
        name="vpn",
        services=[
            Service(
                additional_properties={"cap_add": ["NET_ADMIN"]},
                hostport=1194,
                image="nubacuk/docker-openvpn:aarch64",
                ingress=[
                    Ingress(
                        domain="vpn.example.com",
                        hostport=1194,
                        port=1194,
                        protocol="udp",
                    )
                ],
                name="openvpn",
                restart="always",
                volumes=["/etc/openvpn"],
            ),
        ],
    ),
    Project(
        description="test project to demonstrate inter service connectivity",
        name="test",
        services=[
            Service(
                env={"TARGET": "cost concerned people", "INFORMANT": "http://test-informant:8080"},
                image="otomi/nodejs-helloworld:v1.2.13",
                ingress=[Ingress(domain="hello.example.com")],
                name="master",
                volumes=["/data/bla", "/etc/dida"],
            ),
            Service(
                env={"TARGET": "boss"},
                image="otomi/nodejs-helloworld:v1.2.13",
                name="informant",
                additional_properties={"cpus": 0.1},
            ),
        ],
    ),
    Project(
        description="whoami service",
        name="whoami",
        services=[
            Service(image="traefik/whoami:latest", ingress=[Ingress(domain="whoami.example.com")], name="web"),
        ],
    ),
]
