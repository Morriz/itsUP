---
description: The closed set of files an agent edits to deploy or change a service in itsUP — a project directory in the projects/ repo and one encrypted secrets file in the secrets/ repo.
---
# itsUP Projects and Secrets — Concept

## What

A **project** is the unit of deployment: a single directory in the `projects/` git repo, named
for the project, holding a small, predictable set of files.

- **`itsup-project.yml`** — routing declaration in itsUP's own schema: whether the project is
  enabled, its ingress (service, router, port, domain), egress, and TLS.
- **`docker-compose.yml`** — the service definition(s) as raw Docker Compose. It defines only
  the services; itsUP injects routing, Traefik labels, networks, and DNS when it generates the
  deployable stack.
- **`files/`** — deployable auxiliary payload the services mount: scripts, declarative data
  files, and similar. Compose references them as `./files/<name>`; artifact generation mirrors
  `projects/<project>/files/` into the generated upstream stack, so the deployed artifact is
  self-contained. Multi-line container logic lives here as `.sh` source files invoked
  explicitly through the container's interpreter — readable (`0644`), never marked
  executable, and never inline in compose YAML.
- **Optional bind-mount directories** (e.g. `config/`, `certs/`) — project-specific files the
  services mount. Service state is bind-mounted, never kept in named volumes.

A **secret** is one file per project in the separate `secrets/` git repo:

- **`<project>.enc.txt`** — SOPS/age-encrypted key/value secrets. This is the only tracked form.
- **`<project>.txt`** — the decrypted plaintext, produced transiently for editing. It is
  gitignored and never committed.

That is the whole surface. To add or change a deployed service, an agent edits these files and
commits — nothing else constitutes a project. Both repos live under the itsUP install root, so
an agent editing the files directly works against their real paths under that root.

## Why

Keeping a project to two declarative files plus one encrypted secret makes "edit a project" a
closed, predictable operation an agent can perform without rediscovering bespoke structure each
time. Routing lives in `itsup-project.yml` and services in `docker-compose.yml` so the compose
input can come straight from a vendor's published stack while itsUP owns all the infrastructure
wiring around it.

Secrets are encrypted at rest and decrypted only transiently because the repo is shared and
pushed to a remote. The plaintext form is gitignored so a decrypt-edit-commit cycle cannot leak
secrets into git history — but that same rule means an un-encrypted edit is invisible to git and
must be re-encrypted before it is committed, or it is silently lost.

## See Also

- ~/.teleclaude/docs/infra/procedure/itsup-gitops-workflow.md
- ~/.teleclaude/docs/infra/concept/itsup-operating-model.md
