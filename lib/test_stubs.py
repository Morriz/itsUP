import yaml

from lib.models import Plugin, Project, Service

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
        domain="home.example.com",
        name="home-assistant",
        services=[
            Service(name="192.168.1.111", passthrough=True, port=443),
        ],
    ),
    Project(
        description="itsUP API running on the host",
        domain="itsup.example.com",
        name="itsUP",
        services=[
            Service(name="host.docker.internal", port=8888),
        ],
    ),
    Project(
        description="VPN server",
        domain="vpn.example.com",
        entrypoint="openvpn",
        name="vpn",
        services=[
            Service(
                additional_properties={"cap_add": ["NET_ADMIN"]},
                hostport=1194,
                image="nubacuk/docker-openvpn:aarch64",
                name="openvpn",
                port=1194,
                protocol="udp",
                restart="always",
                volumes=["/etc/openvpn"],
            ),
        ],
    ),
    Project(
        description="test project to demonstrate inter service connectivity",
        domain="hello.example.com",
        entrypoint="master",
        name="test",
        services=[
            Service(
                env={"TARGET": "cost concerned people", "INFORMANT": "http://test-informant:8080"},
                image="otomi/nodejs-helloworld:v1.2.13",
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
        domain="whoami.example.com",
        entrypoint="web",
        name="whoami",
        services=[
            Service(image="traefik/whoami:latest", name="web"),
        ],
    ),
]
