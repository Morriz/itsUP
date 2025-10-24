# itsUP Architecture V2 - Everything in Git

**Core Principle:** Everything is in git except the SOPS encryption key.

---

## File Structure

```
Main Repo (Morriz/itsUP):
├── samples/                        # Sample files (copy on init)
│   ├── env                        # Runtime config (ITSUP_ROOT, PYTHON_ENV)
│   ├── traefik.yml                # Infrastructure config (with ${VARS})
│   ├── secrets/
│   │   └── global.txt             # Example secrets file
│   └── example-project/
│       ├── docker-compose.yml     # Example project (with ${VARS})
│       └── traefik.yml            # Example routing config (with ${VARS})
├── itsup                           # CLI entry point
├── commands/                       # CLI subcommands
│   ├── init.py                    # Initialize new installation
│   ├── compose.py                 # Docker compose wrapper
│   └── apply.py                   # Deploy all
├── lib/                            # Python modules
├── tpl/                            # Jinja2 templates (render artifacts)
│   └── proxy/
│       ├── docker-compose.yml.j2
│       ├── traefik.yml.j2         # Static config
│       └── routers-*.yml.j2       # Dynamic routes
└── .env                            # Runtime config (gitignored, from samples/env)

Submodule: projects/ (Morriz/itsUP-projects - PUBLIC):
├── traefik.yml                     # Infrastructure config (COMMITTED!)
└── {project}/
    ├── docker-compose.yml          # Standard docker compose
    └── traefik.yml                 # Routing config

Submodule: secrets/ (Morriz/itsUP-secrets - PRIVATE):
├── global.enc.txt                  # SOPS encrypted
└── {project}.enc.txt               # SOPS encrypted

Generated (gitignored):
├── proxy/                          # Generated proxy config
└── upstream/                       # Generated project configs
```

---

## samples/env (Runtime Config)

**Copied to .env on `itsup init` (user edits for local paths)**

```bash
# Runtime configuration (not infrastructure!)
# These values are machine-specific, not committed to git

# Root directory of itsUP installation (needed for OpenSnitch rules)
ITSUP_ROOT=/home/user/itsup

# Environment (development, production)
# PYTHON_ENV=production
```

**Note:** Only runtime/machine-specific config goes here. Infrastructure config goes in `projects/traefik.yml`.

---

## projects/traefik.yml (Infrastructure Config)

**This file is COMMITTED to the projects/ submodule.**

```yaml
# Infrastructure configuration
# Secrets referenced as ${VAR} - actual values in secrets/global.txt

domain_suffix: instrukt.ai

letsencrypt:
  email: ${LETSENCRYPT_EMAIL}      # From secrets
  staging: false

trusted_ips:
  - 192.168.1.1
  - 172.0.0.0/8
  - 10.0.0.0/8

traefik:
  log_level: DEBUG                  # INFO, DEBUG, WARN
  dashboard_enabled: true
  dashboard_domain: traefik.${domain_suffix}
  dashboard_auth: ${TRAEFIK_ADMIN}  # From secrets (htpasswd format)

middleware:
  rate_limit:
    enabled: true
    average: 100                    # requests per second
    burst: 50

  headers:
    ssl_redirect: true
    sts_seconds: 31536000
    sts_include_subdomains: true
    sts_preload: true

plugins:
  crowdsec:
    enabled: true
    version: v1.2.0
    collections:
      - crowdsecurity/linux
      - crowdsecurity/traefik
      - crowdsecurity/http-cve
      - crowdsecurity/sshd
      - crowdsecurity/whitelist-good-actors
      - crowdsecurity/appsec-virtual-patching
    scenarios:
      - crowdsecurity/http-admin-interface-probing
      - crowdsecurity/http-backdoors-attempts
      - crowdsecurity/http-bad-user-agent
      - crowdsecurity/http-crawl-non_statics
      - crowdsecurity/http-generic-bf
      - crowdsecurity/http-open-proxy
      - crowdsecurity/http-path-traversal-probing
      - crowdsecurity/http-probing
      - crowdsecurity/http-sensitive-files
      - crowdsecurity/http-sqli-probing
      - crowdsecurity/http-xss-probing
      - ltsich/http-w00tw00t
    options:
      logLevel: WARN
      updateIntervalSeconds: 60
      defaultDecisionSeconds: 600
      httpTimeoutSeconds: 10
      # Secrets
      apikey: ${CROWDSEC_API_KEY}
      capiMachineId: ${CROWDSEC_CAPI_MACHINE_ID}
      capiPassword: ${CROWDSEC_CAPI_PASSWORD}

versions:
  traefik: v3.2
  crowdsec: v1.6.8
```

**Why this design:**
- ✅ Configuration is declarative and in git
- ✅ Can be shared publicly (no secrets)
- ✅ Secrets referenced as ${VARS}
- ✅ Easy to customize (rate limiting, plugins, etc.)
- ✅ Version pinning in one place

---

## samples/traefik.yml (Sample Config)

**Copied as-is to projects/traefik.yml on `itsup init` (user edits directly)**

```yaml
# Infrastructure configuration
# Edit values below, then commit to git
# Secrets referenced as ${VAR} - actual values in secrets/global.txt

domain_suffix: example.com  # CHANGE THIS

letsencrypt:
  email: ${LETSENCRYPT_EMAIL}  # From secrets/global.txt
  staging: false  # Set to true for testing

trusted_ips:
  - 192.168.1.1  # Your router IP
  - 172.0.0.0/8  # Docker networks
  - 10.0.0.0/8   # Private networks

traefik:
  log_level: INFO  # DEBUG, INFO, WARN
  dashboard_enabled: true
  dashboard_domain: traefik.${domain_suffix}
  dashboard_auth: ${TRAEFIK_ADMIN}  # From secrets (htpasswd)

middleware:
  rate_limit:
    enabled: true
    average: 100  # requests per second
    burst: 50

  headers:
    ssl_redirect: true
    sts_seconds: 31536000
    sts_include_subdomains: true
    sts_preload: true

plugins:
  crowdsec:
    enabled: true
    version: v1.2.0
    collections:
      - crowdsecurity/linux
      - crowdsecurity/traefik
      - crowdsecurity/http-cve
      - crowdsecurity/sshd
      - crowdsecurity/whitelist-good-actors
      - crowdsecurity/appsec-virtual-patching
    scenarios:
      - crowdsecurity/http-admin-interface-probing
      - crowdsecurity/http-backdoors-attempts
      - crowdsecurity/http-bad-user-agent
      - crowdsecurity/http-crawl-non_statics
      - crowdsecurity/http-generic-bf
      - crowdsecurity/http-open-proxy
      - crowdsecurity/http-path-traversal-probing
      - crowdsecurity/http-probing
      - crowdsecurity/http-sensitive-files
      - crowdsecurity/http-sqli-probing
      - crowdsecurity/http-xss-probing
      - ltsich/http-w00tw00t
    options:
      logLevel: WARN
      updateIntervalSeconds: 60
      defaultDecisionSeconds: 600
      httpTimeoutSeconds: 10
      # Secrets from secrets/global.txt
      apikey: ${CROWDSEC_API_KEY}
      capiMachineId: ${CROWDSEC_CAPI_MACHINE_ID}
      capiPassword: ${CROWDSEC_CAPI_PASSWORD}

versions:
  traefik: v3.2
  crowdsec: v1.6.8
```

---

## samples/secrets/global.txt

**Example secrets file (user copies and fills in)**

```bash
# Infrastructure secrets
# Copy to secrets/global.txt and fill in actual values

# Let's Encrypt
LETSENCRYPT_EMAIL=admin@example.com

# Traefik Dashboard (htpasswd format: htpasswd -nb admin password)
TRAEFIK_ADMIN=admin:$apr1$xyz...

# CrowdSec
CROWDSEC_API_KEY=your-api-key-here
CROWDSEC_CAPI_MACHINE_ID=your-machine-id
CROWDSEC_CAPI_PASSWORD=your-capi-password

# Shared SMTP (if using)
SMTP_HOST=smtp-relay.brevo.com
SMTP_USER=your-smtp-user
SMTP_PASSWORD=your-smtp-password

# Shared API keys
OPENAI_API_KEY=sk-proj-your-key
```

---

## samples/example-project/docker-compose.yml

**Example project to copy when adding new project**

```yaml
services:
  web:
    image: nginx:alpine
    environment:
      # Reference secrets from secrets/
      API_KEY: ${MY_PROJECT_API_KEY}
    volumes:
      - ./html:/usr/share/nginx/html
    networks:
      - traefik

networks:
  traefik:
    external: true
```

---

## samples/example-project/traefik.yml

**Sample routing config (copy and edit)**

```yaml
enabled: true

ingress:
  - service: web
    domain: my-app.example.com  # CHANGE THIS
    port: 80
```

---

## Workflow

### Initial Setup (New Installation)

```bash
# 1. Clone main repo
git clone git@github.com:Morriz/itsUP.git
cd itsUP

# 2. Initialize (copies samples → projects)
./itsup init

# Copies:
#   - samples/env → .env
#   - samples/traefik.yml → projects/traefik.yml
#   - samples/secrets/global.txt → secrets/global.txt

# 3. Edit configuration
vim projects/traefik.yml
# (Change domain_suffix, trusted_ips, etc.)

vim secrets/global.txt
# (Add actual API keys, passwords, etc.)

# 4. Encrypt secrets
cd secrets/
sops -e global.txt > global.enc.txt
git add global.enc.txt
git commit -m "Initial secrets"
git push

# 5. Commit infrastructure config
cd ../projects/
git add traefik.yml
git commit -m "Initial infrastructure config"
git push

# 6. Deploy
cd ..
./itsup apply
```

### Adding a New Project

```bash
# 1. Copy example
cp -r samples/example-project projects/my-app

# 2. Edit docker-compose.yml
vim projects/my-app/docker-compose.yml

# 3. Configure routing
vim projects/my-app/traefik.yml

# 4. Add project secrets (if needed)
echo "MY_APP_API_KEY=secret123" >> secrets/my-app.txt
cd secrets/
sops -e my-app.txt > my-app.enc.txt
git add my-app.enc.txt
git commit -m "Add my-app secrets"
git push

# 5. Commit project
cd ../projects/
git add my-app/
git commit -m "Add my-app project"
git push

# 6. Deploy
cd ..
./itsup compose my-app up -d
```

### Updating Infrastructure Config

```bash
# Edit committed config
vim projects/traefik.yml
# (e.g., enable a new CrowdSec collection)

# Commit changes
cd projects/
git add traefik.yml
git commit -m "Enable new CrowdSec collection"
git push

# Apply changes
cd ..
./itsup apply
```

---

## Template Rendering Flow

```
Input Files:
  projects/traefik.yml        (infrastructure config, committed)
  projects/*/docker-compose.yml  (projects, committed)
  projects/*/traefik.yml      (routing, committed)
  secrets/*.txt               (secrets, decrypted, gitignored)

Rendering:
  tpl/proxy/traefik.yml.j2 + projects/traefik.yml + secrets/*.txt
    → proxy/traefik/traefik.yml

  tpl/proxy/docker-compose.yml.j2 + projects/traefik.yml
    → proxy/docker-compose.yml

  tpl/proxy/routers-http.yml.j2 + projects/*/traefik.yml
    → proxy/traefik/routers-http.yml

  projects/my-app/docker-compose.yml + secrets/*.txt
    → upstream/my-app/docker-compose.yml (with labels injected)

Deployment:
  docker compose up -d (proxy, upstreams)
```

---

## CLI Commands

### itsup init

**Initialize new installation from samples**

```bash
./itsup init [--non-interactive]
```

**Behavior:**
1. Check if projects/traefik.yml exists (abort if yes)
2. Check if secrets/ submodule exists
3. Copy samples/env → .env
4. Copy samples/traefik.yml → projects/traefik.yml
5. Copy samples/secrets/global.txt → secrets/global.txt
6. Show next steps (edit files, encrypt, commit)

**Example:**

```bash
$ ./itsup init

itsUP Initialization
====================

✓ Copied samples/env → .env
✓ Copied samples/traefik.yml → projects/traefik.yml
✓ Copied samples/secrets/global.txt → secrets/global.txt

Next steps:
1. Edit .env:
   - Set ITSUP_ROOT to absolute path of this directory

2. Edit projects/traefik.yml:
   - Change domain_suffix to your domain
   - Adjust trusted_ips for your network
   - Configure middleware settings

3. Edit secrets/global.txt:
   - Fill in LETSENCRYPT_EMAIL
   - Generate TRAEFIK_ADMIN (htpasswd -nb admin password)
   - Add CROWDSEC_API_KEY and other secrets

4. Encrypt secrets:
   cd secrets && sops -e global.txt > global.enc.txt

5. Commit to git:
   cd projects && git add traefik.yml && git commit -m "Initial config"
   cd ../secrets && git add global.enc.txt && git commit -m "Initial secrets"

6. Deploy:
   ./itsup apply
```

### itsup project add

**Add new project from template**

```bash
./itsup project add <name> [--template=example-project]
```

**Behavior:**
1. Copy samples/example-project → projects/<name>
2. Create empty secrets/<name>.txt if needed
3. Show next steps (edit files)

**Example:**

```bash
$ ./itsup project add my-app

✓ Copied samples/example-project → projects/my-app/
  - docker-compose.yml
  - traefik.yml
✓ Created secrets/my-app.txt

Next steps:
1. Edit projects/my-app/docker-compose.yml (configure services)
2. Edit projects/my-app/traefik.yml (change domain, port)
3. Add secrets to secrets/my-app.txt (if needed)
4. Encrypt: cd secrets && sops -e my-app.txt > my-app.enc.txt
5. Commit to git
6. Deploy: ./itsup compose my-app up -d
```

---

## Migration from Current System

**One-time migration script to convert existing setup:**

```bash
# bin/migrate-to-v2.py

# 1. Extract infrastructure config from db.yml → projects/traefik.yml
# 2. Extract secrets from db.yml → secrets/global.txt (and per-project)
# 3. Convert projects from db.yml → projects/*/docker-compose.yml
# 4. Preserve upstream/ for comparison
# 5. Generate new artifacts and diff with old
```

---

## Benefits

### Everything in Git
- ✅ Infrastructure config committed (projects/traefik.yml)
- ✅ Project configs committed (projects/*/)
- ✅ Only secrets encrypted and separate
- ✅ No magic external db.yml
- ✅ No .env with config (only runtime vars)

### Shareability
- ✅ Can open-source projects/ submodule
- ✅ Community can contribute stack definitions
- ✅ secrets/ stays private, encrypted

### Simplicity
- ✅ Standard docker-compose.yml
- ✅ Minimal custom formats (just traefik.yml)
- ✅ Clear separation (config vs secrets)
- ✅ `itsup init` sets up everything

### Maintainability
- ✅ Plugin config in one place (projects/traefik.yml)
- ✅ Version pinning visible
- ✅ Easy to customize per-environment
- ✅ Git history tracks all changes

---

## Questions Answered

**Q: Where does db.yml go?**
A: It disappears. Infrastructure config → `projects/traefik.yml` (committed). Secrets → `secrets/global.txt` (encrypted).

**Q: Where are plugin configurations?**
A: In `projects/traefik.yml` (CrowdSec collections, scenarios, etc.)

**Q: Where are versions pinned?**
A: In `projects/traefik.yml` under `versions:`

**Q: What about .env?**
A: Only for machine-specific runtime config (ITSUP_ROOT, PYTHON_ENV). Copied from `samples/env`. Not committed to git. All infrastructure config goes in `projects/traefik.yml`.

**Q: How to share my setup?**
A: `projects/` submodule is public! Just don't share `secrets/`.

**Q: How to initialize new installation?**
A: `itsup init` copies samples → projects, prompts for config, creates structure.

**Q: What if I want different config per environment?**
A: Have different projects/ repos: `itsUP-projects-prod`, `itsUP-projects-staging`. Switch submodule.

---

## Next: Update Implementation Plan

Now update todos/IMPLEMENTATION.md to reflect this architecture.
