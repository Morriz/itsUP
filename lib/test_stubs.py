import yaml

from lib.models import Ingress, Plugin, Project, Router, Service

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
            Service(
                ingress=[Ingress(domain="home.example.com", passthrough=True, port=443, router=Router.tcp)],
                host="192.168.1.111",
            ),
        ],
    ),
    Project(
        description="Home Assistant http passthrough for letsencrypt",
        enabled=False,
        name="home-assistant-challenge",
        services=[
            Service(
                ingress=[
                    Ingress(
                        domain="home.example.com",
                        path_prefix="/.well-known/acme-challenge/",
                        passthrough=True,
                        port=80,
                    )
                ],
                host="192.168.1.111",
            ),
        ],
    ),
    Project(
        description="itsUP API running on the host",
        name="itsUP",
        services=[
            Service(ingress=[Ingress(domain="itsup.example.com", port=8888)], host="172.17.0.1"),
        ],
    ),
    Project(
        description="Minio service",
        enabled=False,
        name="minio",
        services=[
            Service(
                command='server --console-address ":9001" /data',
                env={
                    "MINIO_ROOT_USER": "root",
                    "MINIO_ROOT_PASSWORD": "xx",
                },
                image="minio/minio:latest",
                ingress=[
                    Ingress(domain="minio-api.example.com", port=9000, router=Router.tcp),
                    Ingress(domain="minio-ui.example.com", port=9001),
                ],
                host="app",
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
                        router="udp",
                    )
                ],
                host="openvpn",
                restart="always",
                volumes=["/etc/openvpn"],
            ),
        ],
    ),
    Project(
        description="whoami service",
        name="whoami",
        services=[
            Service(image="traefik/whoami:latest", ingress=[Ingress(domain="whoami.example.com")], host="web"),
        ],
    ),
]
