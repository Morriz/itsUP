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
- [Apps included](#apps-included)
- [Prerequisites](#prerequisites)
- [Dev/ops tools](#devops-tools)
  - [utility functions](#utility-functions)
  - [Utility scripts](#utility-scripts)
  - [Makefile](#makefile)
  - [DNS Honeypot](#dns-honeypot)
  - [Container Security Monitor](#container-security-monitor)
- [Howto](#howto)
  - [Install \& run](#install--run)
  - [Configure services](#configure-services)
    - [Scenario 1: Adding an upstream service that will be deployed and managed](#scenario-1-adding-an-upstream-service-that-will-be-deployed-and-managed)
    - [Scenario 2: Adding a TLS passthrough endpoint](#scenario-2-adding-a-tls-passthrough-endpoint)
    - [Scenario 3: Adding a TCP endpoint](#scenario-3-adding-a-tcp-endpoint)
    - [Scenario 4: Adding a local (host) endpoint](#scenario-4-adding-a-local-host-endpoint)
    - [Additional docker properties](#additional-docker-properties)
  - [Configure plugins](#configure-plugins)
    - [CrowdSec](#crowdsec)
  - [Using the Api \& OpenApi spec](#using-the-api--openapi-spec)
  - [Webhooks](#webhooks)
  - [Backup and restore](#backup-and-restore)
    - [How the backup system works](#how-the-backup-system-works)
    - [Configure S3 backup settings](#configure-s3-backup-settings)
    - [Perform a manual backup](#perform-a-manual-backup)
    - [Set up scheduled backups](#set-up-scheduled-backups)
    - [Restore from a backup](#restore-from-a-backup)
  - [Threat Intelligence Reports](#threat-intelligence-reports)
    - [Configure AbuseIPDB API](#configure-abuseipdb-api)
    - [Generate threat report manually](#generate-threat-report-manually)
    - [Set up automated daily reports](#set-up-automated-daily-reports)
  - [OpenVPN server with SSH access](#openvpn-server-with-ssh-access)
    - [1. Initialize the configuration files and certificates](#1-initialize-the-configuration-files-and-certificates)
    - [2. Create a client file](#2-create-a-client-file)
    - [3. Retrieve the client configuration with embedded certificates and place in github workflow folder](#3-retrieve-the-client-configuration-with-embedded-certificates-and-place-in-github-workflow-folder)
    - [4. SSH access](#4-ssh-access)
    - [5. Make sure port 1194 is portforwarding the UDP protocol.](#5-make-sure-port-1194-is-portforwarding-the-udp-protocol)
- [Questions one might have](#questions-one-might-have)
  - [What about Nginx?](#what-about-nginx)
  - [Does this scale to more machines?](#does-this-scale-to-more-machines)
- [Disclaimer](#disclaimer)

## Key concepts

### Single source of truth

One file (`db.yml`) is used for all the infra and workloads it creates and manages, to ensure a predictable and reliable automated workflow.
This means abstractions are used which means a trade off between flexibility and reliability, but the stack is easily modified and enhanced to meet your needs. We strive to mirror docker compose functionality, which means no concessions are necessary from a docker compose enthusiast's perspective.

### Managed proxy setup

itsUP generates and manages `proxy/docker-compose.yml` which operates Traefik in a zero-downtime configuration:

**Architecture:**
- Traefik using Linux SO_REUSEPORT for zero-downtime updates (defaults to 1 replica)
- Host networking mode allows multiple instances to bind to same ports simultaneously
- Kernel load-balances incoming connections between scaled instances
- Users can scale manually: `docker compose up -d --scale traefik=N` (e.g., N=2 for high availability)
- Docker socket access secured via dockerproxy (wollomatic/socket-proxy) on localhost

**Capabilities:**
1. Terminate TLS and forward tcp/udp traffic over an encrypted network to listening endpoints
2. Passthrough TLS to endpoints (most people have secure Home Assistant setups already)
3. Open host ports if needed to choose a new port (openvpn service does exactly that)
4. Zero-downtime configuration updates via rolling deployment

### Managed service deployments & updates

itsUP generates and manages `upstream/{project}/docker-compose.yml` files to deploy container workloads as defined as a service in `db.yml`.
This centralizes and abstracts away the plethora of custom docker compose setups that are mostly uniform in their approach anyway, so controlling their artifacts from one source of truth makes a lot of sense.

### <sup>\*</sup>Zero downtime?

Like with all docker orchestration platforms (even Kubernetes) this is dependent on the containers:

- are healthchecks correctly implemented?
- Are SIGHUP signals respected to shutdown within an acceptable time frame?
- Are the containers stateless?

**Smart Change Detection:**

itsUP implements smart change detection that only performs rollouts when necessary:
- Compares Docker Compose config hashes (stored in container labels)
- Detects image updates, environment changes, volume changes, etc.
- Skips rollout if nothing changed (instant operation)
- Automatically performs zero-downtime rollout when changes detected

**Rollout Process:**

When changes are detected, itsUP will rollout via `docker rollout`:

1. Scale to double the current replicas (1→2, 2→4, etc. depending on your scale setting)
2. Wait for new containers to be healthy (max 60s with healthcheck, otherwise 10s)
3. Kill old containers and wait for drain
4. Remove old containers, leaving the same number of new replicas running

**Cost:** ~15 seconds when changes detected, instant when nothing changed.

_What about stateful services?_

It is surely possible to deploy stateful services but beware that those might not be good candidates for the `docker rollout` automation. In order to update those services it is strongly advised to first read the upgrade documentation for the newer version and follow the prescribed steps. More mature databases might have integrated these steps in the runtime, but expect that to be an exception. So, to garner correct results you are on your own and will have to read up on your chosen solutions.

## Apps included

- [traefik/traefik](https://github.com/traefik/traefik): the famous L7 routing proxy that manages letsencrypt certificates
- [minio/minio](https://github.com/minio/minio): S3 storage
- [nubacuk/docker-openvpn](https://github.com/nuBacuk/docker-openvpn): vpn access to the host running this stack
- [traefik/whoami](https://github.com/traefik/whoami): to demonstrate that headers are correctly passed along

## Prerequisites

**Tools:**

- [docker](https://www.docker.com) daemon and client
- docker [rollout](https://github.com/Wowu/docker-rollout) plugin
- [openvpn](https://openvpn.net): for testing vpn access (optional)

**Infra:**

- Portforwarding of port `80` and `443` to the machine running this stack. This stack MUST overtake whatever routing you now have, but don't worry, as it supports your home assistant setup and forwards any traffic it expects to it (if you finish the pre-configured `home-assistant` project in `db.yml`)
- A wildcard dns domain like `*.itsup.example.com` that points to your home ip. This allows to choose whatever subdomain for your services. You may of course choose and manage any domain in a similar fashion for a public service, but I suggest not going through such trouble for anything private.

## Dev/ops tools

### utility functions

Source `lib/functions.sh` to get:

- `dcp <cmd> [service]`: Smart proxy management with zero-downtime
  - `dcp up` - Smart update all proxy services (detects changes, only rollout if needed)
  - `dcp up traefik` - Smart update traefik only
  - `dcp restart [service]` - Smart restart (defaults to traefik)
  - `dcp logs -f` - Regular docker compose passthrough for other commands

- `dcu <project> <cmd> [service]`: Smart upstream management
  - `dcu myproject up` - Smart update all services (auto-rollout when changed)
  - `dcu myproject restart myservice` - Smart restart specific service
  - `dcu myproject logs -f` - Regular docker compose passthrough

- `dca <cmd>`: Run docker compose command for all upstreams: `dca ps`

- `dcpx <service> <cmd>`: Execute command in proxy container
  - Example: `dcpx traefik 'rm -rf /etc/acme/acme.json'`

- `dcux <project> <service> <cmd>`: Execute command in upstream container
  - Example: `dcux test web env`

**Smart Behavior:**
- `up` and `restart` commands use Python's smart detection (via `update_proxy()`/`update_upstream()`)
- Other commands pass through to docker compose directly
- Zero-downtime rollouts only happen when actual changes detected

In effect these wrapper commands achieve the same as when going into an `upstream/*` folder and running `docker compose` there, but with added intelligence.
I don't want to switch folders/terminals all the time and want to keep a "project root" history of my commands so I choose this approach.

### Utility scripts

- ~~`bin/update-certs.py`: pull certs and reload the proxy if any certs were created or updated. You could run this in a crontab every week if you want to stay up to date.~~ (Obsolete since migration to Treaefik)
- `bin/write-artifacts.py`: after updating `db.yml` you can run this script to generate new artifacts.
- `bin/validate-db.py`: also ran from `bin/write-artifacts.py`
- `bin/requirements-update.sh`: You may want to update requirements once in a while ;)

### Makefile

A comprehensive Makefile is provided for common operations. Run `make help` to see all available targets:

```bash
make help              # Show all available commands
make install           # Install dependencies
make test              # Run all tests
make lint              # Run linter
make format            # Format code
make validate          # Validate db.yml
make apply             # Apply configuration changes
make rollout           # Apply with zero-downtime rollout
make backup            # Backup upstream directory to S3
```

**DNS Honeypot management:**

```bash
make dns-up            # Start DNS honeypot
make dns-down          # Stop DNS honeypot
make dns-restart       # Restart DNS honeypot
make dns-logs          # Tail DNS honeypot logs
```

**Container Security Monitor:**

```bash
make monitor-start     # Start container security monitor and tail logs
make monitor-stop      # Stop container security monitor
make monitor-cleanup   # Run cleanup mode to review blacklist
make monitor-logs      # Tail security monitor logs
make monitor-report    # Generate threat intelligence report
```

### DNS Honeypot

All container DNS traffic is routed through a DNS honeypot (`dns-honeypot` container) that logs all queries and responses. This is essential for the container security monitoring system.

The DNS honeypot is managed via `proxy/docker-compose-dns.yml` and runs dnsmasq with query logging enabled. It integrates with the proxy network to intercept all container DNS requests.

### Container Security Monitor

Real-time container security monitoring that detects compromised containers by identifying hardcoded IP connections through DNS correlation analysis.

**Key Features:**

- DNS correlation detection (connections without DNS = malware)
- Real-time Docker events integration
- OpenSnitch cross-reference (optional)
- iptables blocking (optional)
- Automatic IP list management with hot-reload
- Historical analysis with timestamp resumption

**Quick Start:**

```bash
# Start monitor with full protection
make monitor-start FLAGS="--use-opensnitch --block"

# Stop monitor
make monitor-stop

# View logs
make monitor-logs
```

**📖 For complete documentation, see [monitor/README.md](monitor/README.md)**

This includes:
- Architecture and detection logic
- Configuration options
- False positive handling
- Testing guide
- Performance characteristics

## Howto

### Install & run

These are the scripts to install everything and start the proxy and api so that we can receive incoming challenge webhooks:

1. `bin/install.sh`: creates a local `.venv` and installs all python project deps.
2. `bin/start-all.sh`: starts the proxy (docker compose) and the api server (uvicorn).
3. `bin/apply.py`: applies all of `db.yml` with smart zero-downtime updates.
4. `bin/api-logs.sh`: tails the output of the api server.

But before doing so please configure your stuff:

### Configure services

1. Copy `.env.sample` to `.env` and set the correct info (comments should be self explanatory).
2. Copy `db.yml.sample` to `db.yml` and edit your project and their services (see explanations below).

Project and service configuration is explained below with the following scenarios. Please also check `db.yml.sample` as it contains more examples.

#### Scenario 1: Adding an upstream service that will be deployed and managed

Edit `db.yml` and add your projects with their service(s). Any service that is given an `image: ` prop will be deployed with `docker compose`.
Example:

```yaml
projects:
  ...
  - description: whoami service
    name: whoami
    services:
      - image: traefik/whoami:latest
        ingress:
          - domain: whoami.example.com
        host: web
```

Run `bin/apply.py` to write all artifacts and deploy/update relevant docker stacks.

#### Scenario 2: Adding a TLS passthrough endpoint

Add a service with ingress and set `passthrough: true`.
Example:

```yaml
projects:
  ...
  - description: Home Assistant passthrough
    enabled: true
    name: home-assistant
    services:
      - ingress:
        - domain: home.example.com
          passthrough: true
          port: 443
        host: 192.168.1.111
```

If you also need port 80 to listen for http challenges for your endpoint (home-assistant may do its own), then you may also add:

```yaml
  ...
      - ingress:
        ...
        - domain: home.example.com
          passthrough: true
          path_prefix: /.well-known/acme-challenge/
          port: 80
```

(Port 80 is disallowed for any other other cases.)

#### Scenario 3: Adding a TCP endpoint

Add a service with ingress and set `router: tcp`.
Example:

```yaml
projects:
  ...
  - description: Minio service
    name: minio
    services:
      - command: server --console-address ":9001" /data
        env:
          MINIO_ROOT_USER: root
          MINIO_ROOT_PASSWORD: xx
        host: app
        image: minio/minio:latest
        ingress:
          - domain: minio-api.example.com
            port: 9000
            router: tcp
          - domain: minio-ui.example.com
            port: 9001
        volumes:
          - /data
```

#### Scenario 4: Adding a local (host) endpoint

You can expose an existing service that is already running on the host by creating a service:

- without an `image` prop
- targeting the host from within docker
- configuring it's ingress

Example:

```yaml
projects:
  ...
  - description: itsUP API running on the host
    name: itsUP
    services:
      - ingress:
          - domain: itsup.example.com
            port: 8888
        host: 172.17.0.1 # change this to host.docker.internal when on Docker Desktop
```

#### Additional docker properties

One can add additional docker properties to a service by adding them to the `additional_properties` dictionary:

```yaml
additional_properties:
  cpus: 0.1
```

The following docker service properties exist at the service root level and MUST NOT be added via `additional_properties`:

- command
- depends_on
- env
- image
- port
- name
- restart
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

**Step 4: add ip (or cidr) to whitelist**

```
dcpx crowdsec 'cscli allowlists create me -d "my dev ips"'
dcpx crowdsec csli allowlists add me 123.123.123.0/24
```

### Using the Api & OpenApi spec

The API allows openapi compatible clients to do management on this stack (ChatGPT works wonders).

Generate the spec with `api/extract-openapi.py`.

All endpoints do auth and expect either:

- an incoming Bearer token
- `X-API-KEY` header
- `apikey` query param

to be set to `.env/API_KEY`.

Exception: Only github webhook endpoints (check for annotation `@app.hooks.register(...`) get it from the `github_secret` header.

### Webhooks

Webhooks are used for the following:

1. to receive updates to this repo, which will result in a `git pull` and `bin/apply.py` to update any changes in the code. The provided project with `name: itsUP` is used for that, so DON'T delete it if you care about automated updates to this repo.
2. to receive incoming github webhooks (or GET requests to `/update-upstream?project=bla&service=dida`) that result in rolling up of a project or specific service only.

One GitHub webhook listening to `workflow_job`s is provided, which needs:

- the hook you will register in the github project to end with `/hook?project=bla&service=dida` (`service` optional), and the `github_secret` set to `.env/API_KEY`.

I mainly use GitHub workflows and created webhooks for my individual projects, so I can just manage all webhooks in one place.

**NOTE:**

When using crowdsec this webhook is probably not coming in as it exits the Azure cloud (public IP range), which is also host to many malicious actors that spin up ephemeral intrusion tools. To still receive signals from github you can use a vpn setup as the one used in this repo (check `.github/workflows/test.yml`).

### Backup and restore

itsUP includes a robust backup system that archives your service configurations and uploads them to S3-compatible storage for safekeeping. The backup functionality is implemented in `bin/backup.py`.

#### How the backup system works

The backup system:

1. Creates a tarball (`itsup.tar.gz`) of your `upstream` directory, which contains all your service configurations
2. Excludes any folders specified in the `BACKUP_EXCLUDE` environment variable
3. Uploads the tarball to an S3-compatible storage service
4. Implements backup rotation, keeping only the 10 most recent backups
5. Automatically adds timestamps to backup filenames for versioning

#### Configure S3 backup settings

To use the backup functionality, you need to configure the following environment variables in your `.env` file:

```

AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_S3_HOST=your_s3_host
AWS_S3_REGION=your_s3_region
AWS_S3_BUCKET=your_bucket_name
BACKUP_EXCLUDE=folder1,folder2 # Optional: comma-separated list of folders to exclude from backup

```

#### Perform a manual backup

To manually run a backup:

```sh
sudo .venv/bin/python bin/backup.py
```

#### Set up scheduled backups

For automated backups, you can set up a cron job. For example, to run a backup daily at 2 AM:

```
0 5 * * * cd /path/to/itsup && .venv/bin/python bin/backup.py
```

#### Restore from a backup

To restore from a backup, you'll need to:

1. Download the desired backup from your S3 bucket
2. Extract the tarball to restore your configurations:

```sh
tar -xzf itsup.tar.gz.{timestamp} -C /path/to/itsup/
```

3. Run `bin/apply.py` to apply the restored configurations

### Threat Intelligence Reports

itsUP includes automated threat analysis that correlates blacklisted IPs with threat intelligence from AbuseIPDB, performing reverse DNS lookups and WHOIS queries to identify potential threat actors.

#### Configure AbuseIPDB API

To enable threat intelligence lookups, add your AbuseIPDB API key to `.env`:

```
ABUSEIPDB_API_KEY=your_api_key_here
```

Get a free API key at https://www.abuseipdb.com/register (1,000 checks/day on free tier).

#### Generate threat report manually

```bash
make monitor-report
```

This generates `reports/potential_threat_actors.csv` with:

- Network ranges and abuse confidence scores
- Organization details and contact information
- Usage type (Datacenter, Hosting, ISP, etc.)
- Tor exit node detection
- Last reported timestamp

The script is incremental - it only analyzes NEW IPs not already in the report.

#### Set up automated daily reports

Add to root's crontab to run daily at 4 AM:

```bash
sudo crontab -e
```

Add this line:

```
0 4 * * * cd /path/to/itsup && make monitor-report >> /var/log/threat_analysis.log 2>&1
```

### OpenVPN server with SSH access

This setup contains a project called "vpn" which runs an openvpn service that gives ssh access. To bootstrap it:

#### 1. Initialize the configuration files and certificates

```
dcu vpn run vpn-openvpn ovpn_genconfig -u udp4://vpn.itsup.example.com
dcu vpn run vpn-openvpn ovpn_initpki
```

Save the signing passphrase you created.

#### 2. Create a client file

```
export CLIENTNAME='github'
dcu vpn run vpn-openvpn easyrsa build-client-full $CLIENTNAME
```

Save the client passphrase you created as it will be used for `OVPN_PASSWORD` below.

#### 3. Retrieve the client configuration with embedded certificates and place in github workflow folder

```
dcu vpn run vpn-openvpn ovpn_getclient $CLIENTNAME combined > .github/workflows/client.ovpn
```

**IMPORTANT:** Now change `udp` to `udp4` in the `remote: ...` line to target UDP with IPv4 as docker is still not there.

Test access (expects local `openvpn` installed):

```
sudo openvpn .github/workflows/client.ovpn
```

Now save the `$OVPN_USER_KEY` from `client.ovpn`'s `<key>$OVPN_USER_KEY</key>` and remove the `<key>...</key>`.
Also save the `$OVPN_TLS_AUTH_KEY` from `<tls-auth...` section and remove it.

Add the secrets to your github repo

- `OVPN_USERNAME`: `github`
- `OVPN_PASSWORD`: the client passphrase
- `OVPN_USER_KEY`
- `OVPN_TLS_AUTH_KEY`

#### 4. SSH access

In order for ssh access by github, create a private key and add the pub part to the `authorized_keys` on the host:

```

ssh-keygen -t ed25519 -C "your_email@example.com"
cat ~/.ssh/id_ed25519.pub >> ~/.ssh/authorized_keys

```

Add the secrets to GitHub:

- `SERVER_HOST`: the hostname of this repo's api server
- `SERVER_USERNAME`: the username that has access to your host's ssh server
- `SSH_PRIVATE_KEY`: the private key of the user

#### 5. Make sure port 1194 is portforwarding the UDP protocol.

Now we can start the server and expect all to work ok.

If you wish to revoke a cert or do something else, please visit this page: [kylemanna/docker-openvpn/blob/master/docs/docker-compose.md](https://github.com/kylemanna/docker-openvpn/blob/master/docs/docker-compose.md)

## Questions one might have

### Why Traefik over Nginx?

Traefik was chosen for several key reasons:
- **Dynamic configuration**: Automatically picks up container changes via Docker labels
- **Automatic cert management**: Manages Let's Encrypt certificates gracefully with built-in ACME support
- **Zero-downtime updates**: With SO_REUSEPORT, can run multiple instances on same ports
- **Kubernetes-like labels**: Familiar L7 routing configuration for those from K8s background
- **No manual cert rotation**: Unlike Nginx which requires cron jobs for certificate renewal

While Nginx can be faster in raw performance (~40%), Traefik's automation and zero-downtime capabilities make it the better choice for this use case.

### Does this scale to more machines?

In the future we might consider expanding this setup to use docker swarm, as it should be easy to do. For now we like to keep it simple.

## Disclaimer

**Don't blame this infra automation tooling for anything going wrong inside your containers!**

I suggest you repeat that mantra now and then and question yourself when things go wrong: where lies the problem?
