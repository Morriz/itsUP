# itsUP <!-- omit in toc -->

_Lean, secure, automated, zero downtime<sup>\*</sup>, poor man's infra for services running in docker._

<img align="center" src="assets/freight-conductor.png">
<p></p>
<p>
Running a home network? Then you may already have a custom setup, probably using docker compose. You might enjoy all the maintenance and tinkering, but you are surely aware of the pitfalls and potential downtime. If you think that is ok, or if you don't want automation, then this stack is probably not for you.
Still interested? Then read on...
</p>

**Table of contents:**

- [Key concepts](#key-concepts)
  - [Single source of truth](#single-source-of-truth)
  - [Managed proxy setup](#managed-proxy-setup)
  - [Managed service deployments \& updates](#managed-service-deployments--updates)
  - [\*Zero downtime?](#zero-downtime)
- [Prerequisites](#prerequisites)
- [Howto](#howto)
  - [Install \& run](#install--run)
  - [Configure services](#configure-services)
  - [Configure plugins](#configure-plugins)
    - [CrowdSec](#crowdsec)
  - [Using the Api \& OpenApi spec](#using-the-api--openapi-spec)
    - [Webhooks](#webhooks)
- [Dev/ops tools](#devops-tools)
  - [utility functions for dev workflow](#utility-functions-for-dev-workflow)
  - [Utility scripts](#utility-scripts)
- [Questions one might have](#questions-one-might-have)
  - [What about Nginx?](#what-about-nginx)
  - [Does this scale to more machines?](#does-this-scale-to-more-machines)
- [Disclaimer](#disclaimer)

## Key concepts

### Single source of truth

One file (`db.yml`) is used for all the infra and workloads it creates and manages, to ensure a predictable and reliable automated workflow.
This means abstractions are used which means a trade off between flexibility and reliability, but the stack is easily modified and enhanced to meet your needs. We strive to mirror docker compose functionality, which means no concessions are necessary from a docker compose enthusiast's perspective.

### Managed proxy setup

itsUP generates and manages `proxy/docker-compose.yml` that runs two proxies in series (tcp -> web), with only the first exposing ports, to be able to:

1. do TLS passthrough to existing endpoints (most people have secure Home Assistant setups already)
2. terminate TLS and forward securely to managed endpoints over an encrypted `proxynet` docker network

### Managed service deployments & updates

itsUP generates and manages `upstream/{project}/docker-compose.yml` files to deploy container workloads as defined as a service in `db.yml`.
This centralizes and abstracts away the plethora of custom docker compose setups that are mostly uniform in their approach anyway, so controlling their artifacts from one source of truth makes a lot of sense.

### <sup>\*</sup>Zero downtime?

Like with all docker orchestration platforms (even Kubernetes) this is dependent on the containers:

- are healthchecks correctly implemented?
- Are SIGHUP signals respected to shutdown within an acceptable time frame?
- Are the containers stateless?

itsUP will rollout changes by:

1. bringing up a new container and wait till it is healthy (if it has a health check then max 60s, otherwise assumes it is healthy after 10s)
2. kill the old container and wait for it to drain, then removes it

_What about stateful services?_

It is surely possible to deploy stateful services but beware that those might not be good candidates for the `docker rollout` automation. In order to update those services it is strongly advised to first read the upgrade documentation for the newer version and follow the prescribed steps. More mature databases might have integrated these steps in the runtime, but expect that to be an exception. So, to garner correct results you are on your own and will have to read up on your chosen solutions.

## Prerequisites

**Tools:**

- [docker](https://www.docker.com) daemon and client
- docker [rollout](https://github.com/Wowu/docker-rollout) plugin

**Infra:**

- Portforwarding of port `80` and `443` to the machine running this stack. This stack MUST overtake whatever routing you now have, but don't worry, as it supports your home assistant setup and forwards any traffic it expects to it (if you finish the pre-configured `home-assistant` project in `db.yml`)
- A wildcard dns domain like `*.itsup.example.com` that points to your home ip. This allows to choose whatever subdomain for your services. You may of course choose and manage any domain in a similar fashion for a public service, but I suggest not going through such trouble for anything private.

## Howto

### Install & run

These are the scripts to install everything and start the proxy and api so that we can receive incoming challenge webhooks:

1. `bin/install.sh`: creates a local `.venv` and installs all python project deps.
2. `bin/start-all.sh`: starts the proxy (docker compose) and the api server (uvicorn).
3. `bin/apply.py`: applies all of `db.yml`.
4. `bin/api-logs.sh`: tails the output of the api server. (The

But before doing so please configure your stuff:

### Configure services

1. Copy `.env.sample` to `.env` and set the correct info (comments should be self explanatory).
2. Copy `db.yml.sample` to `db.yml` and edit your project and their services (see explanations below).

Project and service configuration is explained below with the following scenarios:

**Adding an upstream service that will be deployed and managed:**

1. Edit `db.yml` and add your projects with their service(s), and make sure the project has `entrypoint: {the name of your entrypoint svc}`.
2. Run `bin/apply.py` to write all artifacts and deploy/update relevant docker stacks.

**Adding a passthrough endpoint:**

1. Add a project without `entrypoint:` and one service, which now need `name`, `domain` and `passthrough: true`.
2. Run `bin/apply.py` to roll out the changes.

**Adding a local (host) endpoint:**

1. Add a project without `entrypoint:` and one service, which only need `name` and `domain`.
2. Run `bin/apply.py` to roll out the changes.

**Additional docker properties:**

One can add additional docker properties to a service by adding them to the `additional_properties` dictionary:

```yaml
additional_properties:
  cpus: 0.1
```

The following docker service properties exist at the service root level and MUST NOT be added via `additional_properties`:

- command
- env
- image
- port
- name
- volumes

(Also see `lib/models.py`)

### Configure plugins

You can enable and configure plugins in `db.yml`. Right now we support the following:

#### CrowdSec

[CrowdSec](https://www.crowdsec.net) can run as a container via plugin [crowdsec-bouncer-traefik-plugin](https://github.com/maxlerebourg/crowdsec-bouncer-traefik-plugin).

**Step 1: generate api key**

First set `enable: true`, run `bin/write-artifacts.py`, and bring up the `crowdsec` container:

```
docker compose up -d crowdsec
```

Now we can execute the command to get the key:

```
docker compose exec crowdsec cscli bouncers add crowdsecBouncer
```

Put the resulting api key in the `plugins.crowdsec.apikey` configuration in `db.yml` and apply with `bin/apply.py`.
Crowdsec is now running and wired up, but does not use any blocklists yet. Those can be managed manually, but preferable is to become part of the community by creating an account with CrowdSec to get access and contribute to the community blocklists, as well as view results in your account's dashboards.

**Step 2: connect your instance with the CrowdSec console**

After creating an account create a machine instance in the console, and register the enrollment key in your stack:

```
docker compose exec crowdsec cscli console enroll ${enrollment key}
```

**Step 3: subscribe to 3rd party blocklists**

In the [security-engines](https://app.crowdsec.net/security-engines) section select the "Blocklists" of your engine and choose some blocklists of interest.
Example:

- Free proxies list
- Firehol SSL proxies list
- Firehol cruzit.com list

### Using the Api & OpenApi spec

The API allows openapi compatible clients to do management on this stack (ChatGPT works wonders).

Generate the spec with `api/extract-openapi.py`.

All endpoints do auth and expect an incoming Bearer token to be set to `.env/API_KEY`.

Exception: Only github webhook endpoints (check for annotation `@app.hooks.register(...`) get it from the `github_secret` header.

#### Webhooks

Webhooks are used for the following:

1. to receive updates to this repo, which will result in a `git pull` and `bin/apply.py` to update any changes in the code. The provided project with `name: itsUP` is used for that, so DON'T delete it if you care about automated updates to this repo.
2. to receive incoming github webhooks (or GET requests to `/update-upstream?project=bla&service=dida`) that result in rolling up of a project or specific service only.

One GitHub webhook listening to `workflow_job`s is provided, which needs:

- the hook you will register in the github project to end with `/hook?project=bla&service=dida` (`service` optional), and the `github_secret` set to `.env/API_KEY`.

I mainly use GitHub workflows and created webhooks for my individual projects, so I can just manage all webhooks in one place.

## Dev/ops tools

### utility functions for dev workflow

Source `lib/functions.sh` to get:

- `dcp`: run a `docker compose` command targeting the proxy stack (`proxy` + `terminate` services): `dcp logs -f`
- `dcu`: run a `docker compose` command targeting a specific upstream: `dcu test up`
- `dca`: run a `docker compose` command targeting all upstreams: `dca ps`
- `dcpx`: execute a command in one of the proxy containers: `dcpx traefik-web 'rm -rf /etc/acme/acme.json && shutdown' && dcp up`
- `dcux`: execute a command in one of the upstream containers: `dcux test test-informant env`

In effect these wrapper commands achieve the same as when going into an `upstream/\*`folder and running`docker compose` there.
I don't want to switch folders/terminals all the time and want to keep a "project root" history of my commands so I choose this approach.

### Utility scripts

- `bin/update-certs.py`: pull certs and reload the proxy if any certs were created or updated. You could run this in a crontab every week if you want to stay up to date.
- `bin/write-artifacts.py`: after updating `db.yml` you can run this script to generate new artifacts.
- `bin/validate-db.py`: also ran from `bin/write-artifacts.py`
- `bin/requirements-update.sh`: You may want to update requirements once in a while ;)

## Questions one might have

### What about Nginx?

As you may have noted there is a lot of functionality based on Nginx in this repo. I started out using their proxy, but later on ran into the problem of their engine not picking up upstream changes, learning that only the paid Nginx+ does that. I heavily relied on kubernetes in the past years and such was not an issue in their `ingress-NGINX` controller. When I found that Traefik does not suffer this, AND manages letsencrypt certs gracefully, AND gives us label based L7 functionality (like in Kubernetes), I decided to integrate that instead. Weary about its performance though, I intended to keep both approaches side by side. The Nginx part is not working anymore, but I left the code for others to see how one can overcome certain problems in that ecosystem. If one would like to use Nginx for some reason (it is about 40% faster), it is very easy to switch back. But be aware it implies hooking up the hacky `bin/update-certs.py` script to a cron tab for automatic cert rotation.

### Does this scale to more machines?

In the future we might consider expanding this setup to use docker swarm, as it should be easy to do. For now we like to keep it simple.

## Disclaimer

**Don't blame this infra automation tooling for anything going wrong inside your containers!**

I suggest you repeat that mantra now and then and question yourself when things go wrong: where lies the problem?
