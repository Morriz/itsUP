import yaml

from lib.models import Project, Service

with open("db.yml.sample", encoding="utf-8") as f:
    test_db = yaml.safe_load(f)

test_projects = [
    Project(
        name="home-assistant",
        description="Home Assistant passthrough",
        domain="home.example.com",
        services=[
            Service(name="192.168.1.111", passthrough=True, port=443),
        ],
    ),
    Project(
        name="itsUP",
        description="itsUP API running on the host",
        domain="itsup.example.com",
        services=[
            Service(name="172.17.0.1", port=8888),
        ],
    ),
    Project(
        name="test",
        description="test project to demonstrate inter service connectivity",
        domain="hello.example.com",
        entrypoint="master",
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
            ),
        ],
    ),
    Project(
        name="whoami",
        description="whoami service",
        domain="whoami.example.com",
        entrypoint="web",
        services=[
            Service(image="traefik/whoami:latest", name="web"),
        ],
    ),
]
