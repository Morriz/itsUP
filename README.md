# Doup

*/duːp/ (sounds like doop)*

## Lean + low cost docker compose infra

Single machine multi docker compose architecture with a low cpu/storage footprint and near-zero<sup>*</sup> downtime.

It runs two nginx proxies in series (proxy -> terminate) to be able to:
- terminate SSL/TLS
- do SSL/TLS passthrough
- target many upstream endpoints
 
**Advantages:**

- shared docker network: encrypted intra-node communication (over a shared network named `proxynet`)
- near-zero-downtime

**<sup>*</sup>Near-zero-downtime?**

Well, all nodes that get rotated do not incur downtime, yet nginx neads a reload signal. During low traffic that will allow for a graceful handling of outstanding http sessions and no downtime, but may be problematic if nginx needs to wait for a magnitude of open sessions. In that case a timeout will force the last open sessions to be terminated.
This approach is a very reliable and cheap approach to achieve zero downtime.

**Prerequisites:**

- [docker](https://www.docker.com)
- docker [rollout](https://github.com/Wowu/docker-rollout) plugin

## Howto

### Configure

1. Copy `db.yaml.sample` to `db.yaml` and edit your project and their services (see explanations below).
2. Copy `.env.sample` to `.env` and set the correct info.
3. [OPTIONAL] In case you want to run the api create an `API_KEY` (`openssl rand -hex 16`) and put in `.env`.

### Install & run

Install everything and start the proxy so that we can receive incoming challenge webhooks.

1. `bin/install.sh`
2. `bin/start-proxy.sh`

### Adding an upstream svc

1. Edit `db.yaml` and add your projects with their service(s), and make sure the project has `upstream: true`.
3. Run `bin/apply.py` to get certs, write needed artifacts, update relevant docker stacks and reload nginx.

### Adding a passthrough endpoint

1. Edit `db.yaml` and add your service(s), which now need  `domain`, `svc` and `passthrough: true`.
2. Run `bin/apply.py` to roll out the changes.

### API (optional)

You can run an API to allow openapi compatible clients to do management on this stack (ChatGPT works wonders).

Start the API with `bin/start-api.sh`.
Generate the spec with `api/extract-openapi.py`.

All endpoints do auth and expect an incoming Bearer token to be set to `.env/API_KEY`.

Exception: Only github webhook endpoints (check for annotation `@app.hooks.register(...`) get it from the `github_secret` header.

#### Webhooks

Webhooks are used for the following:
1. to receive updates to this repo, which will result in a `git pull` and `bin/apply.py` to update any changes in the code. The provided project with `name: doup` is used for that, so DON'T delete it if you care about automated updates to this repo.
2. to receive incoming github webhooks (or GET requests to `/update-upstream?project=bla&service=dida`) that result in rolling up of a project or specific service only.

One GitHub webhook listening to `workflow_job`s is provided, which needs the hook you will register in the github project to end with `/hook?project=bla&service=dida` (`service` optional), and the `github_secret` set to `.env/API_KEY`.

I mainly use GitHub workflows and created webhooks for my individual projects, so I can just manage all webhooks in one place. 

### Dev/ops tools

#### functions

Source `lib/functions.sh` to get:

- `dcp`: run a `docker compose` command targeting the proxy stack (`proxy` + `terminate` services): `dcp logs -f`
- `dcu`: run a `docker compose` command targeting a specific upstream: `dcu test up`
- `dca`: run a `docker compose` command targeting all upstreams: `dca ps`

In effect these wrapper commands achieve the same as when going into an `upstream/*` folder and running `docker compose` there.
I don't want to switch folders/terminals all the time and want to keep history of my commands so I choose this approach.

#### Scripts

- `bin/update-certs.py`: pull certs and reload the proxy if any certs were created or updated. You could run this in a crontab every week if you want to stay up to date.
- `bin/write-artifacts.py`: after updating `db.yml` yo ucan run this script to check new artifacts.


## Roadmap

1. Dockerize (and use `docker compose` for) most of the code in this repo (except `bin/host-cmd-listener.sh`, which will listen on the host to a named pipe for commands starting with `docker compose` and perform sanity checks)