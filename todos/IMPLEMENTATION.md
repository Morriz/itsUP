# itsUP V2 - Implementation Plan

**Status:** 📋 Ready to Execute
**Architecture:** V2 - Everything in git except SOPS key

**Read First:**
1. [KEY-INSIGHT.md](KEY-INSIGHT.md) - Why V2 is better
2. [ARCHITECTURE-V2.md](ARCHITECTURE-V2.md) - Complete design
3. [FILE-EXTENSIONS.md](FILE-EXTENSIONS.md) - File naming rules

---

## What We're Building

### Before (Current)
```
db.yml (752 lines, monolithic, gitignored)
  ├── Infrastructure config (plugins, domains, rate limiting)
  ├── Project definitions (services, env, volumes)
  ├── Secrets (duplicated 6+ times)
  └── Routing config

lib/functions.sh (bash layer)
  ├── dcp, dcu wrappers
  └── Complex abstraction

25 bin/* scripts
```

### After (V2)
```
samples/ (in git, committed)
  ├── env                      # Runtime config template
  ├── traefik.yml             # Infrastructure config (with ${VARS})
  ├── secrets/
  │   └── global.txt          # Example secrets
  └── example-project/
      ├── docker-compose.yml
      └── traefik.yml

projects/ (PUBLIC submodule, committed)
  ├── traefik.yml             # Infrastructure config (from sample)
  └── {project}/
      ├── docker-compose.yml  # Standard docker compose
      └── traefik.yml         # Routing config

secrets/ (PRIVATE submodule, encrypted)
  ├── global.enc.txt
  └── {project}.enc.txt

itsup (Python CLI)
  ├── itsup init              # Copy samples → projects
  ├── itsup compose           # Smart sync + docker compose
  └── itsup apply             # Regenerate all + deploy
```

**Key Changes:**
- ❌ **db.yml eliminated** - replaced by samples/ → projects/
- ✅ **Everything in git** - except SOPS key
- ✅ **Simple initialization** - `itsup init` copies files (no rendering)
- ✅ **Standard docker compose** - no custom DSL

---

## Execution Strategy

Work is ordered in **SELF-CONTAINED STEPS** that can each be:
- Completed independently
- Tested in isolation
- Committed to git
- Picked up fresh after context clear

Each step produces **WORKING STATE** - no half-broken commits.

---

## STEP 1: Setup SOPS Infrastructure (30 min)

**Goal:** Get SOPS working locally with age encryption

**Prerequisites:** None (start here)

**Deliverables:**
- Age key generated
- SOPS installed and configured
- Test encrypt/decrypt working

**Implementation:**

```bash
# 1.1: Install SOPS and age
sudo apt-get update
sudo apt-get install -y age
wget https://github.com/getsops/sops/releases/download/v3.8.1/sops-v3.8.1.linux.arm64
sudo mv sops-v3.8.1.linux.arm64 /usr/local/bin/sops
sudo chmod +x /usr/local/bin/sops

# 1.2: Generate age key
mkdir -p ~/.config/sops/age
age-keygen -o ~/.config/sops/age/keys.txt

# 1.3: Save public key for later (used in .sops.yaml)
grep "public key:" ~/.config/sops/age/keys.txt
# Example output: age1ql3z7hjy54pw3hyww5ayyfg7zqgvc7w3j2elw8zmrj2kg5sfn9aqmcac8p

# 1.4: Test encryption/decryption
echo "TEST_SECRET=hello123" > /tmp/test.txt
PUBLIC_KEY=$(grep "public key:" ~/.config/sops/age/keys.txt | cut -d: -f2 | tr -d ' ')
sops --age $PUBLIC_KEY --encrypt /tmp/test.txt > /tmp/test.enc.txt
sops --decrypt /tmp/test.enc.txt
# Should output: TEST_SECRET=hello123
rm /tmp/test*
```

**Success Criteria:**
- [ ] `sops --version` works
- [ ] `age --version` works
- [ ] Age key exists at `~/.config/sops/age/keys.txt`
- [ ] Test encrypt/decrypt successful

**Commit:** `setup: Install SOPS and age, generate encryption key`

---

## STEP 2: Create GitHub Repositories (10 min)

**Goal:** Create the two submodule repositories

**Prerequisites:** STEP 1 complete

**Deliverables:**
- `Morriz/itsUP-secrets` (private repo)
- `Morriz/itsUP-projects` (public repo)

**Implementation:**

```bash
# 2.1: Create repositories via GitHub MCP or web UI

# Create private secrets repo
# - Name: itsUP-secrets
# - Private: Yes
# - Description: SOPS-encrypted secrets for itsUP infrastructure
# - Initialize with README: Yes

# Create public projects repo
# - Name: itsUP-projects
# - Private: No
# - Description: Docker Compose stack definitions - Share your infrastructure!
# - Initialize with README: Yes
```

**Success Criteria:**
- [ ] https://github.com/Morriz/itsUP-secrets exists (private)
- [ ] https://github.com/Morriz/itsUP-projects exists (public)
- [ ] Both have README.md from initialization

**Commit:** N/A (GitHub operations)

---

## STEP 3: Initialize Secrets Submodule (45 min)

**Goal:** Setup secrets/ with SOPS, git hooks, structure

**Prerequisites:** STEP 1, STEP 2 complete

**Deliverables:**
- secrets/ directory initialized
- SOPS configured
- Git hooks installed
- Test secrets encrypted

**Implementation:**

```bash
# 3.1: Clone secrets repo as submodule
cd /home/morriz/srv
git submodule add git@github.com:Morriz/itsUP-secrets.git secrets
cd secrets/

# 3.2: Create .sops.yaml (get public key from STEP 1)
PUBLIC_KEY=$(grep "public key:" ~/.config/sops/age/keys.txt | cut -d: -f2 | tr -d ' ')
cat > .sops.yaml <<EOF
creation_rules:
  - path_regex: \.enc\.txt$
    age: ${PUBLIC_KEY}
EOF

# 3.3: Create .gitignore (ignore decrypted files)
cat > .gitignore <<'EOF'
# Ignore decrypted secrets (only track encrypted)
*.txt
!*.enc.txt
!README.txt
EOF

# 3.4: Create README.md
cat > README.md <<'EOF'
# itsUP Secrets

SOPS-encrypted secrets for itsUP infrastructure.

## Structure

- `global.enc.txt` - Shared secrets (SMTP, API keys)
- `{project}.enc.txt` - Project-specific secrets

## Usage

Secrets are automatically encrypted/decrypted by git hooks.

### Manual Operations

```bash
# Edit (decrypts, opens $EDITOR, re-encrypts on save)
sops global.enc.txt

# Decrypt
sops -d global.enc.txt > global.txt

# Encrypt
sops -e global.txt > global.enc.txt
```

## Setup

1. Get age private key from team lead
2. Save to `~/.config/sops/age/keys.txt`
3. Git hooks auto-decrypt on checkout/pull
EOF

# 3.5: Create git hooks directory
mkdir -p .git/hooks

# 3.6: Create post-checkout hook (auto-decrypt after pull)
cat > .git/hooks/post-checkout <<'HOOK'
#!/bin/bash
# Auto-decrypt secrets after checkout/pull

set -e

SECRETS_DIR="$(git rev-parse --show-toplevel)"
cd "$SECRETS_DIR"

echo "🔓 Decrypting secrets..."

# Decrypt all .enc.txt files
for enc_file in *.enc.txt; do
    if [ -f "$enc_file" ]; then
        dec_file="${enc_file%.enc.txt}.txt"
        if sops -d "$enc_file" > "$dec_file" 2>/dev/null; then
            echo "  ✓ $dec_file"
        else
            echo "  ✗ $dec_file (failed - check age key)"
        fi
    fi
done

echo "✓ Secrets decrypted"
HOOK

chmod +x .git/hooks/post-checkout

# 3.7: Create pre-commit hook (auto-encrypt before commit)
cat > .git/hooks/pre-commit <<'HOOK'
#!/bin/bash
# Auto-encrypt secrets before commit

set -e

SECRETS_DIR="$(git rev-parse --show-toplevel)"
cd "$SECRETS_DIR"

# Check if any .txt files are staged
if git diff --cached --name-only --diff-filter=ACM | grep -q '\.txt$'; then
    echo "🔒 Encrypting secrets..."

    # Encrypt all changed .txt files
    git diff --cached --name-only --diff-filter=ACM | grep '\.txt$' | while read txt_file; do
        if [ -f "$txt_file" ]; then
            enc_file="${txt_file%.txt}.enc.txt"
            if sops -e "$txt_file" > "$enc_file"; then
                git add "$enc_file"
                echo "  ✓ $enc_file"
            else
                echo "  ✗ $enc_file (encryption failed)"
                exit 1
            fi
        fi
    done

    echo "✓ Secrets encrypted"
fi
HOOK

chmod +x .git/hooks/pre-commit

# 3.8: Create test secret file
cat > global.txt <<'EOF'
# Shared secrets for all projects
SMTP_HOST=smtp-relay.brevo.com
SMTP_USER=test@example.com
SMTP_PASSWORD=test-password-will-replace-later
CROWDSEC_API_KEY=test-key
EOF

# 3.9: Encrypt test file
sops -e global.txt > global.enc.txt

# 3.10: Test hooks work
rm global.txt  # Delete decrypted
git add global.enc.txt .sops.yaml .gitignore README.md
git commit -m "Initial secrets structure with SOPS"
git checkout HEAD  # Triggers post-checkout hook
ls -la global.txt  # Should exist (decrypted by hook)

# 3.11: Push to remote
git push -u origin main

# 3.12: Return to main repo
cd ..
git add .gitmodules secrets/
git commit -m "Add secrets submodule with SOPS encryption"
```

**Success Criteria:**
- [ ] secrets/ is git submodule
- [ ] .sops.yaml exists with correct age key
- [ ] Git hooks are executable
- [ ] Test encrypt/decrypt works
- [ ] Hook auto-decrypts on checkout
- [ ] Hook auto-encrypts on commit
- [ ] Pushed to GitHub (only .enc.txt tracked)

**Commit:** `Add secrets submodule with SOPS encryption`

---

## STEP 4: Initialize Projects Submodule (30 min)

**Goal:** Setup projects/ structure

**Prerequisites:** STEP 2 complete

**Deliverables:**
- projects/ submodule initialized
- README.md with structure docs
- .gitignore configured

**Implementation:**

```bash
# 4.1: Clone projects repo as submodule
cd /home/morriz/srv
git submodule add git@github.com:Morriz/itsUP-projects.git projects
cd projects/

# 4.2: Create README.md
cat > README.md <<'EOF'
# itsUP Projects

Docker Compose stack definitions for itsUP infrastructure.

## Structure

**Infrastructure Config:**
- `traefik.yml` - Infrastructure-wide configuration (domain, plugins, middleware)

**Projects:**
Each project is a directory containing:
- `docker-compose.yml` - Standard Docker Compose (copy-paste from anywhere!)
- `traefik.yml` - Minimal routing configuration

## Adding a New Project

```bash
# 1. Create directory
mkdir my-app

# 2. Add standard docker-compose.yml
# (copy from Docker Hub, your existing setup, etc.)

# 3. Create traefik.yml for routing
cat > my-app/traefik.yml <<YAML
enabled: true
ingress:
  - service: web
    domain: my-app.example.com
    port: 3000
YAML

# 4. Reference secrets from secrets/ submodule
# In docker-compose.yml, use ${SECRET_VAR} syntax
```

## traefik.yml Schema

**Infrastructure (projects/traefik.yml):**
```yaml
domain_suffix: example.com

letsencrypt:
  email: ${LETSENCRYPT_EMAIL}      # From secrets
  staging: false

traefik:
  log_level: INFO
  dashboard_enabled: true
  dashboard_auth: ${TRAEFIK_ADMIN}  # From secrets

middleware:
  rate_limit:
    enabled: true
    average: 100
    burst: 50

plugins:
  crowdsec:
    enabled: true
    apikey: ${CROWDSEC_API_KEY}    # From secrets
```

**Project Routing (projects/{name}/traefik.yml):**
```yaml
enabled: true|false

ingress:
  - service: web              # Docker compose service name
    domain: app.example.com   # Domain for routing
    port: 3000                # Container port
    router: http|tcp|udp      # Default: http
    path_prefix: /api         # Optional: path-based routing
    hostport: 8080            # Optional: expose on host
    passthrough: true|false   # Optional: TLS passthrough
    tls_sans:                 # Optional: SAN certificate
      - alt1.example.com
      - alt2.example.com
```

## Examples

See existing projects for real-world examples.
EOF

# 4.3: Create .gitignore (don't track data volumes)
cat > .gitignore <<'EOF'
# Ignore data volumes (should be in upstream/)
*/data/
*/var/
*/logs/
*/*.db
*/*.sqlite

# Keep structure
!*/docker-compose.yml
!*/traefik.yml
!traefik.yml
EOF

# 4.4: Commit and push
git add README.md .gitignore
git commit -m "Initial projects structure"
git push -u origin main

# 4.5: Return to main repo
cd ..
git add .gitmodules projects/
git commit -m "Add projects submodule"
```

**Success Criteria:**
- [ ] projects/ is git submodule
- [ ] README.md documents structure
- [ ] .gitignore configured
- [ ] Pushed to GitHub

**Commit:** `Add projects submodule`

---

## STEP 5: Create samples/ Directory (1 hour)

**Goal:** Create sample files for initialization

**Prerequisites:** None

**Deliverables:**
- samples/env
- samples/traefik.yml
- samples/secrets/global.txt
- samples/example-project/*

**Implementation:**

```bash
# 5.1: Create samples directory structure
mkdir -p samples/secrets
mkdir -p samples/example-project

# 5.2: Create samples/env (runtime config)
cat > samples/env <<'EOF'
# Runtime configuration (machine-specific, not committed to git)
# Copied to .env on `itsup init`

# Root directory of itsUP installation (needed for OpenSnitch rules)
ITSUP_ROOT=/home/user/itsup

# Environment (development, production)
# PYTHON_ENV=production
EOF

# 5.3: Create samples/traefik.yml (infrastructure config)
cat > samples/traefik.yml <<'EOF'
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
EOF

# 5.4: Create samples/secrets/global.txt
cat > samples/secrets/global.txt <<'EOF'
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
EOF

# 5.5: Create samples/example-project/docker-compose.yml
cat > samples/example-project/docker-compose.yml <<'EOF'
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
EOF

# 5.6: Create samples/example-project/traefik.yml
cat > samples/example-project/traefik.yml <<'EOF'
enabled: true

ingress:
  - service: web
    domain: my-app.example.com  # CHANGE THIS
    port: 80
EOF

# 5.7: Add samples/ to git
git add samples/
git commit -m "Add samples/ directory for initialization"
```

**Success Criteria:**
- [ ] samples/env exists
- [ ] samples/traefik.yml exists (no .j2, no .sample)
- [ ] samples/secrets/global.txt exists (no .sample)
- [ ] samples/example-project/* exists
- [ ] All committed to git

**Commit:** `Add samples/ directory for initialization`

---

## STEP 6: Extract Secrets from db.yml (1-2 hours)

**Goal:** Move all secrets from db.yml to secrets/

**Prerequisites:** STEP 3 complete

**Deliverables:**
- secrets/global.txt with actual secrets
- All secrets encrypted
- db.yml backed up

**Implementation:**

Create extraction script:

```python
# bin/extract-secrets.py
#!/usr/bin/env python3
"""Extract secrets from db.yml to secrets/ files"""

import re
import yaml
from pathlib import Path

def is_secret(key: str, value: str) -> bool:
    """Detect if a value is likely a secret"""
    secret_keywords = [
        'password', 'secret', 'key', 'token', 'api', 'auth',
        'smtp', 'db_pass', 'redis_pass', 'api_key', 'htpasswd'
    ]

    key_lower = key.lower()

    # Check key name
    if any(kw in key_lower for kw in secret_keywords):
        return True

    # Check value patterns
    if isinstance(value, str):
        # Long random strings
        if len(value) > 20 and re.match(r'^[A-Za-z0-9+/=_-]+$', value):
            return True
        # JWT/API key patterns
        if value.startswith(('sk-', 'pk-', 'Bearer ', '$apr1$', '$2')):
            return True

    return False

def extract_env_from_dict(data: dict, prefix: str = "") -> dict:
    """Recursively extract all env vars"""
    env_vars = {}

    for key, value in data.items():
        var_name = f"{prefix}_{key}".upper() if prefix else key.upper()

        if isinstance(value, dict):
            env_vars.update(extract_env_from_dict(value, var_name))
        elif isinstance(value, str):
            env_vars[var_name] = value

    return env_vars

def main():
    # Load current db.yml
    with open('db.yml') as f:
        db = yaml.safe_load(f)

    # Create db.yml backup
    with open('db.yml.backup', 'w') as f:
        yaml.dump(db, f)

    # Extract all env vars
    all_vars = {}

    # From plugins
    if 'plugins' in db:
        for plugin, config in db['plugins'].items():
            if isinstance(config, dict):
                vars = extract_env_from_dict(config, f'{plugin}')
                all_vars.update(vars)

    # From projects
    if 'projects' in db:
        for project in db['projects']:
            name = project.get('name', '')
            if 'env' in project:
                vars = extract_env_from_dict(project['env'], name)
                all_vars.update(vars)

    # Separate secrets from non-secrets
    secrets = {}
    config_vars = {}

    for key, value in all_vars.items():
        if is_secret(key, value):
            secrets[key] = value
        else:
            config_vars[key] = value

    # Write secrets to secrets/global.txt
    secrets_dir = Path('secrets')
    with open(secrets_dir / 'global.txt', 'w') as f:
        f.write("# Shared secrets extracted from db.yml\n")
        f.write("# Review and deduplicate before encrypting\n\n")
        for key, value in sorted(secrets.items()):
            f.write(f"{key}={value}\n")

    print(f"✓ Extracted {len(secrets)} secrets to secrets/global.txt")
    print(f"  Review for duplicates (SMTP, OpenAI keys appear multiple times)")
    print(f"\nNext steps:")
    print(f"  1. cd secrets/")
    print(f"  2. Edit global.txt to deduplicate")
    print(f"  3. sops -e global.txt > global.enc.txt")
    print(f"  4. git add global.enc.txt && git commit && git push")

if __name__ == '__main__':
    main()
```

Run extraction:

```bash
# 6.1: Extract secrets
chmod +x bin/extract-secrets.py
bin/extract-secrets.py

# 6.2: Review and deduplicate
cd secrets/
vim global.txt
# Deduplicate SMTP credentials (same in 6 projects)
# Deduplicate OpenAI keys
# Add any missing secrets

# 6.3: Encrypt
sops -e global.txt > global.enc.txt

# 6.4: Commit
git add global.enc.txt
git commit -m "Extract and consolidate secrets from db.yml"
git push

# 6.5: Return to main repo
cd ..
```

**Manual Review Required:**
- Deduplicate SMTP credentials (same in 6 projects)
- Deduplicate OpenAI keys
- Verify no secrets missed

**Success Criteria:**
- [ ] secrets/global.enc.txt exists with all secrets
- [ ] No duplicate secrets
- [ ] db.yml.backup created
- [ ] All encrypted files committed to git

**Commit:**
```bash
cd secrets/
git commit -m "Extract and consolidate secrets from db.yml"
```

---

## STEP 7: Implement `itsup init` Command (2 hours)

**Goal:** Create initialization command

**Prerequisites:** STEP 5 complete

**Deliverables:**
- commands/init.py
- Simple file copy (no rendering)
- Interactive prompts

**Implementation:**

```python
# commands/init.py
"""Initialize new installation from samples"""

import logging
import shutil
from pathlib import Path

import click

logger = logging.getLogger(__name__)

@click.command()
@click.option('--non-interactive', is_flag=True, help='Skip prompts')
def init(non_interactive):
    """
    Initialize new installation from samples

    Copies sample files to create initial configuration
    """
    logger.info("itsUP Initialization")
    logger.info("=" * 50)

    # Check if already initialized
    if Path('projects/traefik.yml').exists():
        logger.error("Already initialized: projects/traefik.yml exists")
        click.echo("\nIf you want to re-initialize, first backup/remove projects/traefik.yml")
        return 1

    # Check submodules exist
    if not Path('projects/.git').exists():
        logger.error("projects/ submodule not initialized")
        click.echo("Run: git submodule update --init --recursive")
        return 1

    if not Path('secrets/.git').exists():
        logger.warning("secrets/ submodule not initialized")
        click.echo("Continuing without secrets submodule...")

    # Copy samples → destinations
    copies = [
        ('samples/env', '.env'),
        ('samples/traefik.yml', 'projects/traefik.yml'),
        ('samples/secrets/global.txt', 'secrets/global.txt'),
    ]

    for src, dst in copies:
        src_path = Path(src)
        dst_path = Path(dst)

        if not src_path.exists():
            logger.warning(f"Sample not found: {src}")
            continue

        # Create parent directory
        dst_path.parent.mkdir(parents=True, exist_ok=True)

        # Copy file
        shutil.copy2(src_path, dst_path)
        logger.info(f"✓ Copied {src} → {dst}")

    # Show next steps
    click.echo("\n" + "=" * 50)
    click.echo("✓ Initialization complete!\n")
    click.echo("Next steps:")
    click.echo("\n1. Edit .env:")
    click.echo("   - Set ITSUP_ROOT to absolute path of this directory")
    click.echo("\n2. Edit projects/traefik.yml:")
    click.echo("   - Change domain_suffix to your domain")
    click.echo("   - Adjust trusted_ips for your network")
    click.echo("   - Configure middleware settings")
    click.echo("\n3. Edit secrets/global.txt:")
    click.echo("   - Fill in LETSENCRYPT_EMAIL")
    click.echo("   - Generate TRAEFIK_ADMIN (htpasswd -nb admin password)")
    click.echo("   - Add CROWDSEC_API_KEY and other secrets")
    click.echo("\n4. Encrypt secrets:")
    click.echo("   cd secrets && sops -e global.txt > global.enc.txt")
    click.echo("\n5. Commit to git:")
    click.echo("   cd projects && git add traefik.yml && git commit -m 'Initial config'")
    click.echo("   cd ../secrets && git add global.enc.txt && git commit -m 'Initial secrets'")
    click.echo("\n6. Deploy:")
    click.echo("   ./itsup apply")
```

Add to main CLI:

```python
# itsup (add import)
from commands.init import init
cli.add_command(init)
```

Test:

```bash
# 7.1: Test in temp directory
mkdir /tmp/test-init
cd /tmp/test-init
git init
git submodule add <projects-url> projects
git submodule add <secrets-url> secrets
cp -r /home/morriz/srv/samples .

# 7.2: Run init
/home/morriz/srv/itsup init

# 7.3: Verify files copied
ls -la .env
ls -la projects/traefik.yml
ls -la secrets/global.txt

# 7.4: Clean up
cd /home/morriz/srv
rm -rf /tmp/test-init
```

**Success Criteria:**
- [ ] `itsup init` creates .env
- [ ] `itsup init` creates projects/traefik.yml
- [ ] `itsup init` creates secrets/global.txt
- [ ] Shows helpful next steps
- [ ] Detects if already initialized

**Commit:** `feat: Add itsup init command for initialization`

---

## STEP 8: Migration Script - db.yml → projects/ (2-3 hours)

**Goal:** Automated migration of current db.yml to new structure

**Prerequisites:** STEP 6, STEP 7 complete

**Deliverables:**
- bin/migrate-v2.py script
- All current projects migrated
- Validation that output matches current system

**Implementation:**

```python
# bin/migrate-v2.py
#!/usr/bin/env python3
"""Migrate current db.yml to V2 architecture"""

import os
import sys
import yaml
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))

def migrate_infrastructure(db: dict) -> dict:
    """Extract infrastructure config from db.yml → projects/traefik.yml"""

    # Extract infrastructure sections
    infra = {}

    # Copy relevant sections
    if 'domain_suffix' in db:
        infra['domain_suffix'] = db['domain_suffix']

    if 'letsencrypt' in db:
        infra['letsencrypt'] = db['letsencrypt']

    if 'trusted_ips' in db:
        infra['trusted_ips'] = db['trusted_ips']

    if 'traefik' in db:
        infra['traefik'] = db['traefik']

    if 'middleware' in db:
        infra['middleware'] = db['middleware']

    if 'plugins' in db:
        infra['plugins'] = db['plugins']

    if 'versions' in db:
        infra['versions'] = db['versions']

    # Replace secrets with ${VAR} references
    infra = replace_secrets_with_vars(infra)

    return infra

def replace_secrets_with_vars(data):
    """Recursively replace secret values with ${VAR} references"""
    # Load secrets map
    secrets = {}
    secrets_file = Path('secrets/global.txt')
    if secrets_file.exists():
        with open(secrets_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    secrets[value.strip()] = key.strip()

    def replace_value(val):
        if isinstance(val, str) and val in secrets:
            return f"${{{secrets[val]}}}"
        return val

    def replace_dict(d):
        if isinstance(d, dict):
            return {k: replace_dict(v) for k, v in d.items()}
        elif isinstance(d, list):
            return [replace_dict(item) for item in d]
        else:
            return replace_value(d)

    return replace_dict(data)

def migrate_project(project: dict) -> tuple[dict, dict]:
    """
    Convert project from db.yml to docker-compose.yml + traefik.yml

    Returns: (docker_compose, traefik_config)
    """
    name = project['name']

    # Build docker-compose.yml
    compose = {
        'services': {},
        'networks': {
            'traefik': {'external': True}
        }
    }

    # Project-level env
    project_env = project.get('env', {})

    for service in project.get('services', []):
        service_name = service['host']
        compose_service = {}

        # Basic fields
        if 'image' in service:
            compose_service['image'] = service['image']
        if 'command' in service:
            compose_service['command'] = service['command']
        if 'depends_on' in service:
            compose_service['depends_on'] = service['depends_on']

        # Environment
        env = {}
        env.update(project_env)
        env.update(service.get('env', {}))
        if env:
            compose_service['environment'] = env

        # Volumes
        if 'volumes' in service:
            compose_service['volumes'] = service['volumes']

        # Networks
        compose_service['networks'] = ['traefik']

        # Additional properties
        if 'additional_properties' in service:
            compose_service.update(service['additional_properties'])

        compose['services'][service_name] = compose_service

    # Build traefik.yml
    traefik = {
        'enabled': project.get('enabled', True),
        'ingress': []
    }

    for service in project.get('services', []):
        for ingress in service.get('ingress', []):
            if not ingress:
                continue

            traefik_ingress = {'service': service['host']}

            for key in ['domain', 'port', 'router', 'path_prefix', 'hostport', 'passthrough']:
                if key in ingress:
                    traefik_ingress[key] = ingress[key]

            if 'tls' in ingress and 'sans' in ingress['tls']:
                traefik_ingress['tls_sans'] = ingress['tls']['sans']

            traefik['ingress'].append(traefik_ingress)

    return compose, traefik

def main():
    # Load db.yml
    with open('db.yml') as f:
        db = yaml.safe_load(f)

    # Backup
    with open('db.yml.v1-backup', 'w') as f:
        yaml.dump(db, f)

    print("Migrating to V2 architecture...")
    print()

    # 1. Migrate infrastructure config
    print("1. Extracting infrastructure config...")
    infra = migrate_infrastructure(db)

    with open('projects/traefik.yml', 'w') as f:
        f.write("# Infrastructure configuration\n")
        f.write("# Migrated from db.yml\n\n")
        yaml.dump(infra, f, default_flow_style=False, sort_keys=False)

    print("   ✓ projects/traefik.yml")

    # 2. Migrate projects
    print("\n2. Migrating projects...")

    for project in db.get('projects', []):
        name = project['name']
        print(f"   {name}...")

        # Create project directory
        project_dir = Path(f'projects/{name}')
        project_dir.mkdir(exist_ok=True)

        # Generate configs
        compose, traefik = migrate_project(project)

        # Write docker-compose.yml
        with open(project_dir / 'docker-compose.yml', 'w') as f:
            yaml.dump(compose, f, default_flow_style=False, sort_keys=False)

        # Write traefik.yml
        with open(project_dir / 'traefik.yml', 'w') as f:
            yaml.dump(traefik, f, default_flow_style=False, sort_keys=False)

        print(f"     ✓ {name}/docker-compose.yml")
        print(f"     ✓ {name}/traefik.yml")

    print("\n" + "=" * 50)
    print("✓ Migration complete!")
    print()
    print("Files created:")
    print("  - db.yml.v1-backup (old format)")
    print("  - projects/traefik.yml (infrastructure)")
    print("  - projects/*/docker-compose.yml (services)")
    print("  - projects/*/traefik.yml (routing)")
    print()
    print("Next steps:")
    print("  1. Review projects/ structure")
    print("  2. cd projects/ && git add . && git commit && git push")
    print("  3. Remove old db.yml: rm db.yml")

if __name__ == '__main__':
    main()
```

Run migration:

```bash
# 8.1: Run migration
chmod +x bin/migrate-v2.py
bin/migrate-v2.py

# 8.2: Review generated files
ls -la projects/traefik.yml
ls -la projects/*/

# 8.3: Validate
./itsup validate

# 8.4: Commit to projects submodule
cd projects/
git add .
git commit -m "Migrate all projects from monolithic db.yml (V2)"
git push

# 8.5: Return to main repo
cd ..
git add db.yml.v1-backup
git commit -m "Create backup before V2 migration"
```

**Success Criteria:**
- [ ] projects/traefik.yml created
- [ ] All projects migrated to projects/*/
- [ ] Secrets replaced with ${VARS}
- [ ] Validation passes
- [ ] Backup created

**Commit:**
```bash
# In projects/:
git commit -m "Migrate all projects from monolithic db.yml (V2)"

# In main repo:
git commit -m "Create backup before V2 migration"
```

---

## STEP 9: Update lib/data.py for V2 (1 hour)

**Goal:** Load from projects/ structure with ${VAR} expansion

**Prerequisites:** STEP 8 complete

**Deliverables:**
- lib/data.py loads from projects/
- Expands ${VARS} from secrets/
- Minimal models

**Implementation:**

```python
# lib/data.py (SIMPLIFIED for V2)
"""Data loading from projects/ and secrets/"""

import logging
import os
import re
from pathlib import Path
from typing import Any

import yaml
from dotenv import dotenv_values
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# === Models ===

class Ingress(BaseModel):
    """Traefik ingress rule"""
    service: str
    domain: str | None = None
    port: int = 80
    router: str = "http"
    path_prefix: str | None = None
    hostport: int | None = None
    passthrough: bool = False
    tls_sans: list[str] = []

class TraefikConfig(BaseModel):
    """Traefik routing configuration"""
    enabled: bool = True
    ingress: list[Ingress] = []

# === Secret Loading ===

def load_secrets() -> dict[str, str]:
    """Load all secrets from secrets/ (decrypted .txt files)"""
    secrets = {}
    secrets_dir = Path("secrets")

    if not secrets_dir.exists():
        logger.warning("secrets/ directory not found")
        return secrets

    # Load global secrets first
    global_file = secrets_dir / "global.txt"
    if global_file.exists():
        secrets.update(dotenv_values(global_file))

    # Load project-specific secrets
    for secret_file in secrets_dir.glob("*.txt"):
        if secret_file.name in ("global.txt", "README.txt"):
            continue
        secrets.update(dotenv_values(secret_file))

    logger.info(f"Loaded {len(secrets)} secrets")
    return secrets

def expand_env_vars(data: Any, secrets: dict[str, str]) -> Any:
    """Recursively expand ${VAR} in data structure"""
    if isinstance(data, dict):
        return {k: expand_env_vars(v, secrets) for k, v in data.items()}
    elif isinstance(data, list):
        return [expand_env_vars(item, secrets) for item in data]
    elif isinstance(data, str):
        # Expand ${VAR} and $VAR
        def replacer(match):
            var_name = match.group(1) or match.group(2)
            return secrets.get(var_name, match.group(0))

        pattern = r'\$\{([^}]+)\}|\$([A-Z_][A-Z0-9_]*)'
        return re.sub(pattern, replacer, data)
    else:
        return data

# === Project Loading ===

def load_infrastructure() -> dict:
    """Load infrastructure config from projects/traefik.yml"""
    traefik_file = Path("projects/traefik.yml")

    if not traefik_file.exists():
        logger.warning("projects/traefik.yml not found, using defaults")
        return {}

    with open(traefik_file) as f:
        config = yaml.safe_load(f)

    # Expand secrets
    secrets = load_secrets()
    config = expand_env_vars(config, secrets)

    return config

def load_project(project_name: str) -> tuple[dict, TraefikConfig]:
    """
    Load project from projects/{name}/

    Returns: (docker_compose_dict, traefik_config)
    """
    project_dir = Path("projects") / project_name

    if not project_dir.exists():
        raise FileNotFoundError(f"Project not found: {project_name}")

    # Load docker-compose.yml
    compose_file = project_dir / "docker-compose.yml"
    if not compose_file.exists():
        raise FileNotFoundError(f"Missing docker-compose.yml for {project_name}")

    with open(compose_file) as f:
        compose = yaml.safe_load(f)

    # Load traefik.yml
    traefik_file = project_dir / "traefik.yml"
    if not traefik_file.exists():
        logger.warning(f"No traefik.yml for {project_name}, using defaults")
        traefik = TraefikConfig()
    else:
        with open(traefik_file) as f:
            traefik_data = yaml.safe_load(f)
            traefik = TraefikConfig(**traefik_data)

    # Expand secrets in compose
    secrets = load_secrets()
    compose = expand_env_vars(compose, secrets)

    return compose, traefik

def list_projects() -> list[str]:
    """List all available projects"""
    projects_dir = Path("projects")
    if not projects_dir.exists():
        return []

    return [
        p.name
        for p in projects_dir.iterdir()
        if p.is_dir()
        and (p / "docker-compose.yml").exists()
        and p.name != ".git"  # Exclude .git directory
    ]

# === Validation ===

def validate_project(project_name: str) -> list[str]:
    """Validate project configuration, return list of errors"""
    errors = []

    try:
        compose, traefik = load_project(project_name)
    except Exception as e:
        return [str(e)]

    # Validate traefik references exist in compose
    services = compose.get('services', {})
    for ingress in traefik.ingress:
        if ingress.service not in services:
            errors.append(
                f"traefik.yml references unknown service: {ingress.service}"
            )

    return errors

def validate_all() -> dict[str, list[str]]:
    """Validate all projects, return dict of project: [errors]"""
    results = {}
    for project in list_projects():
        errors = validate_project(project)
        if errors:
            results[project] = errors
    return results
```

Test:

```bash
# 9.1: Test loading
.venv/bin/python -c "
from lib.data import list_projects, load_project, load_infrastructure
print('Projects:', list_projects())
infra = load_infrastructure()
print('Infrastructure:', infra.get('domain_suffix'))
compose, traefik = load_project('instrukt-ai')
print('Services:', list(compose['services'].keys()))
"

# 9.2: Test validation
./itsup validate
```

**Success Criteria:**
- [ ] Loads from projects/ structure
- [ ] Expands ${VARS} from secrets/
- [ ] TraefikConfig model works
- [ ] No import errors

**Commit:** `refactor: Simplify lib/data.py for V2 architecture`

---

## STEP 10: Rewrite bin/write-artifacts.py for V2 (1 hour)

**Goal:** Generate upstream/* with V2 structure

**Prerequisites:** STEP 9 complete

**Deliverables:**
- Generates upstream/* from projects/
- Smart staleness detection
- Traefik label injection

**Implementation:**

Update bin/write-artifacts.py to use new data loading (keep staleness logic same).

Key changes:
- Load from projects/ instead of db.yml
- Use lib/data.load_project()
- Keep mtime-based staleness detection

**Success Criteria:**
- [ ] Generates all upstream/* correctly
- [ ] Staleness detection works
- [ ] Traefik labels injected
- [ ] Output matches current system

**Commit:** `refactor: Update write-artifacts.py for V2 architecture`

---

## STEP 11: Build Python CLI (itsup) for V2 (2-3 hours)

**Goal:** Complete CLI with all commands

**Prerequisites:** STEP 10 complete

**Deliverables:**
- itsup CLI with init, apply, svc, validate commands
- Smart sync on apply
- Direct docker compose passthrough for svc

**Command Structure:**

```bash
itsup init                    # Initialize from samples
itsup apply                   # Regenerate all + deploy all (up -d)
itsup apply <project>         # Smart sync + deploy one (up -d)
itsup svc <project> <cmd>     # Docker compose passthrough (no sync)
itsup validate [project]      # Validate configs
```

**Implementation:**

```python
# itsup (main CLI entry point)
#!/usr/bin/env python3
"""itsUP CLI - Infrastructure management"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

import click
from lib.logging_config import setup_logging

@click.group()
@click.option('--verbose', '-v', is_flag=True, help='Verbose logging')
def cli(verbose):
    """itsUP - Infrastructure management CLI"""
    setup_logging(verbose=verbose)

# Import subcommands
from commands.init import init
from commands.apply import apply
from commands.svc import svc
from commands.validate import validate

cli.add_command(init)
cli.add_command(apply)
cli.add_command(svc)
cli.add_command(validate)

if __name__ == '__main__':
    cli()
```

```python
# commands/apply.py
"""Apply configurations (regenerate + deploy)"""

import logging
import subprocess
import sys

import click

from lib.data import list_projects
from bin.write_artifacts import sync_upstream, sync_all_upstreams
from lib.proxy import update_proxy, write_proxies

logger = logging.getLogger(__name__)

@click.command()
@click.argument('project', required=False)
@click.option('--force', is_flag=True, help='Force regeneration')
def apply(project, force):
    """
    Apply configurations (regenerate + deploy)

    Examples:
        itsup apply                  # Deploy all (regenerate + up -d)
        itsup apply instrukt-ai      # Deploy one project (smart sync + up -d)
    """
    if project:
        # Apply single project
        logger.info(f"Deploying {project}...")

        # Validate project exists
        projects = list_projects()
        if project not in projects:
            click.echo(f"Error: Project '{project}' not found", err=True)
            click.echo(f"Available: {', '.join(projects)}", err=True)
            sys.exit(1)

        # Smart sync
        logger.info(f"Syncing {project}...")
        sync_upstream(project)

        # Deploy with -d (daemonize)
        upstream_dir = f"upstream/{project}"
        compose_file = f"{upstream_dir}/docker-compose.yml"

        cmd = [
            "docker", "compose",
            "--project-directory", upstream_dir,
            "-p", project,
            "-f", compose_file,
            "up", "-d"
        ]

        logger.info(f"Running: {' '.join(cmd)}")

        try:
            subprocess.run(cmd, check=True)
            logger.info(f"✓ {project} deployed")
        except subprocess.CalledProcessError as e:
            logger.error(f"✗ {project} deployment failed")
            sys.exit(e.returncode)

    else:
        # Apply all
        logger.info("Deploying all projects...")

        # Regenerate proxy configs
        logger.info("Writing proxy configs...")
        write_proxies()

        # Regenerate all upstreams
        logger.info("Writing upstream configs...")
        sync_all_upstreams(force=force)

        # Deploy proxy
        logger.info("Updating proxy...")
        update_proxy()

        # Deploy all upstreams
        logger.info("Deploying all upstreams...")
        for proj in list_projects():
            upstream_dir = f"upstream/{proj}"
            compose_file = f"{upstream_dir}/docker-compose.yml"

            cmd = [
                "docker", "compose",
                "--project-directory", upstream_dir,
                "-p", proj,
                "-f", compose_file,
                "up", "-d"
            ]

            logger.info(f"Deploying {proj}...")
            try:
                subprocess.run(cmd, check=True)
                logger.info(f"  ✓ {proj}")
            except subprocess.CalledProcessError:
                logger.error(f"  ✗ {proj} failed")

        logger.info("✓ Apply complete")
```

```python
# commands/svc.py
"""Service operations (docker compose passthrough)"""

import logging
import subprocess
import sys
from pathlib import Path

import click
import yaml

from lib.data import list_projects

logger = logging.getLogger(__name__)

def complete_project(ctx, param, incomplete):
    """Autocomplete project names"""
    return [p for p in list_projects() if p.startswith(incomplete)]

def complete_svc_command(ctx, param, incomplete):
    """
    Smart completion for svc command:
    - First position: docker compose commands
    - Second+ position: service names from docker-compose.yml
    """
    # Get already-typed arguments
    args = ctx.params.get('command', [])
    project = ctx.params.get('project')

    # First argument after project: docker compose commands
    if len(args) == 0:
        commands = [
            'up', 'down', 'ps', 'logs', 'restart', 'exec',
            'stop', 'start', 'config', 'pull', 'build',
            'kill', 'rm', 'pause', 'unpause', 'top'
        ]
        return [c for c in commands if c.startswith(incomplete)]

    # Second+ argument: service names from docker-compose.yml
    # (useful for: logs <service>, restart <service>, exec <service>, etc.)
    if project:
        compose_file = Path(f"upstream/{project}/docker-compose.yml")

        if compose_file.exists():
            try:
                with open(compose_file) as f:
                    compose = yaml.safe_load(f)
                    services = list(compose.get('services', {}).keys())
                    return [s for s in services if s.startswith(incomplete)]
            except Exception:
                pass

    return []

@click.command(context_settings=dict(
    ignore_unknown_options=True,
    allow_interspersed_args=False
))
@click.argument('project', autocompletion=complete_project)
@click.argument('command', nargs=-1, required=True, type=click.UNPROCESSED, autocompletion=complete_svc_command)
def svc(project, command):
    """
    Service operations (docker compose passthrough, no sync)

    Examples:
        itsup svc instrukt-ai ps           # Check status
        itsup svc instrukt-ai logs -f web  # Tail logs
        itsup svc instrukt-ai restart web  # Restart service
        itsup svc minio exec minio bash    # Shell into container

    Tab completion works for:
        - Project names
        - Docker compose commands
        - Service names
    """
    # Validate project exists
    projects = list_projects()
    if project not in projects:
        click.echo(f"Error: Project '{project}' not found", err=True)
        click.echo(f"Available: {', '.join(projects)}", err=True)
        sys.exit(1)

    # Run docker compose (no sync)
    upstream_dir = f"upstream/{project}"
    compose_file = f"{upstream_dir}/docker-compose.yml"

    cmd = [
        "docker", "compose",
        "--project-directory", upstream_dir,
        "-p", project,
        "-f", compose_file,
        *command
    ]

    logger.debug(f"Running: {' '.join(cmd)}")

    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        sys.exit(e.returncode)
```

```python
# commands/validate.py (already exists, minor update)
"""Validation commands"""

import logging
import sys

import click

from lib.data import validate_all, validate_project

logger = logging.getLogger(__name__)

@click.command()
@click.argument('project', required=False)
def validate(project):
    """
    Validate project configurations

    Examples:
        itsup validate              # Validate all projects
        itsup validate instrukt-ai  # Validate single project
    """
    if project:
        # Validate single project
        errors = validate_project(project)
        if errors:
            click.echo(f"✗ {project}: {len(errors)} error(s)", err=True)
            for error in errors:
                click.echo(f"  - {error}", err=True)
            sys.exit(1)
        else:
            click.echo(f"✓ {project}: valid")
    else:
        # Validate all projects
        all_errors = validate_all()
        if all_errors:
            click.echo(f"✗ {len(all_errors)} project(s) with errors:", err=True)
            for proj, errors in all_errors.items():
                click.echo(f"\n{proj}:", err=True)
                for error in errors:
                    click.echo(f"  - {error}", err=True)
            sys.exit(1)
        else:
            click.echo("✓ All projects valid")
```

Setup and test:

```bash
# 11.1: Create commands/ package
mkdir -p commands
touch commands/__init__.py

# 11.2: Make itsup executable
chmod +x itsup

# 11.3: Install shell completion (Bash)
cat >> ~/.bashrc <<'EOF'

# itsup completion
eval "$(_ITSUP_COMPLETE=bash_source itsup)"
EOF
source ~/.bashrc

# OR for Zsh:
# cat >> ~/.zshrc <<'EOF'
#
# # itsup completion
# eval "$(_ITSUP_COMPLETE=zsh_source itsup)"
# EOF
# source ~/.zshrc

# 11.4: Test CLI
./itsup --help
./itsup init --help
./itsup apply --help
./itsup svc --help
./itsup validate --help

# 11.5: Test completion
./itsup svc <TAB>                    # Should show: instrukt-ai, minio, etc.
./itsup svc instrukt-ai <TAB>        # Should show: up, down, ps, logs, etc.
./itsup svc instrukt-ai logs <TAB>   # Should show service names: web, db, etc.

# 11.6: Test validate
./itsup validate

# 11.7: Test svc (passthrough)
./itsup svc minio ps
./itsup svc instrukt-ai config

# 11.8: Test apply (single project)
./itsup apply minio
# Should: smart sync + up -d

# 11.9: Test apply (all)
./itsup apply
# Should: regenerate everything + deploy all
```

**Success Criteria:**
- [ ] `./itsup --help` shows all commands
- [ ] `itsup init` copies samples
- [ ] `itsup apply` deploys all (up -d)
- [ ] `itsup apply <project>` smart syncs + deploys one (up -d)
- [ ] `itsup svc <project> <cmd>` passes through to docker compose
- [ ] `itsup validate` checks all configs
- [ ] Tab completion works for projects, commands, and service names
- [ ] All commands have good error messages

**Commit:** `feat: Complete itsup CLI with init, apply, svc, validate`

---

## STEP 12: Update Documentation (1 hour)

**Goal:** Update all docs for V2

**Prerequisites:** All previous steps complete

**Deliverables:**
- CLAUDE.md updated
- README.md updated
- Old references removed

**Implementation:**

Update CLAUDE.md:
- Remove db.yml schema
- Add V2 structure
- Document traefik.yml schema
- Update common commands

Update README.md:
- Quick start with V2
- Architecture overview
- Link to CLAUDE.md

**Success Criteria:**
- [ ] CLAUDE.md reflects V2
- [ ] README.md updated
- [ ] No old references

**Commit:** `docs: Update all documentation for V2 architecture`

---

## STEP 13: Cleanup & Testing (2 hours)

**Goal:** Remove old code, comprehensive testing

**Prerequisites:** All previous steps complete

**Deliverables:**
- Clean codebase
- Full system tested
- Migration complete

**Implementation:**

```bash
# 13.1: Remove old files
gio trash db.yml  # No longer needed!
gio trash lib/functions.sh

# 13.2: Test everything
./itsup validate
./itsup compose minio config
./itsup apply --force

# 13.3: Test fresh clone
cd /tmp
git clone --recurse-submodules ~/srv test-clone
cd test-clone
./itsup validate

# 13.4: Clean up
cd ~/srv
rm -rf /tmp/test-clone
```

**Success Criteria:**
- [ ] db.yml removed (or archived)
- [ ] All commands work
- [ ] Fresh clone works
- [ ] No import errors

**Commit:** `cleanup: Remove db.yml and old bash layer (V2 complete)`

---

## Success Criteria Summary

### Architecture
- ✅ db.yml eliminated (replaced by projects/traefik.yml)
- ✅ Everything in git except SOPS key
- ✅ Projects in PUBLIC submodule
- ✅ Secrets in PRIVATE submodule (encrypted)
- ✅ Standard docker-compose.yml (no custom DSL)

### CLI
- ✅ Single `itsup` entry point
- ✅ `itsup init` for initialization
- ✅ Smart sync (staleness detection)
- ✅ Work from root (no cd)

### Security
- ✅ SOPS encryption working
- ✅ Git hooks auto-encrypt/decrypt
- ✅ No secrets in git (only encrypted)

### Simplicity
- ✅ No Jinja2 rendering for samples (just copy)
- ✅ ${VAR} expansion at runtime
- ✅ Clear file structure

---

## Rollback Plan

If any step fails:

```bash
# Restore from backup
mv db.yml.v1-backup db.yml

# Remove V2 changes
git reset --hard HEAD~N

# Clean submodules
git submodule deinit --force projects secrets
```

Each step is atomic and can be reverted independently.

---

## Next Steps After Completion

1. Monitor system for 1 week
2. Open-source projects/ submodule
3. Write blog post
4. Phase 2: Additional optimizations
