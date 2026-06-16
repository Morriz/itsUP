# Environment Variables Reference

Complete reference for environment variables used in itsup infrastructure.

## Infrastructure Variables

### Core Configuration

**From `secrets/itsup.txt`**:

**`TRAEFIK_ADMIN`** (required for proxy artifacts)
- **Purpose**: Basic-auth credentials for the Traefik dashboard and admin routers
- **Used by**: `bin/write_artifacts.py` (`write_middleware_config`, `write_dynamic_routers`) — proxy artifact generation raises `ValueError` if missing
- **Format**: htpasswd line, e.g. generate with `htpasswd -nb admin your-password`
- **Example**: `TRAEFIK_ADMIN=admin:$apr1$...`
- **Note**: The router IP is NOT a secret — it comes from `routerIP` in `projects/itsup.yml` (or netifaces auto-detection), not from an environment variable. See `get_router_ip` in `lib/data.py`.

**`API_SECRET_KEY`** (required for API)
- **Purpose**: Secret key for API authentication
- **Used by**: API server (session encryption, token signing)
- **Example**: `API_SECRET_KEY=$(openssl rand -hex 32)`
- **Security**: Generate with crypto-secure random (32+ bytes)

**`API_ADMIN_TOKEN`** (required for API)
- **Purpose**: Admin authentication token
- **Used by**: API admin endpoints
- **Example**: `API_ADMIN_TOKEN=$(openssl rand -hex 32)`
- **Security**: Never commit plaintext, rotate regularly

### Backup Configuration

**From `secrets/itsup.txt`**:

**`BACKUP_S3_BUCKET`** (required for backups)
- **Purpose**: S3 bucket name for backups
- **Used by**: `bin/backup.py`
- **Example**: `BACKUP_S3_BUCKET=my-backup-bucket`

**`BACKUP_S3_KEY`** (required for backups)
- **Purpose**: AWS access key ID
- **Used by**: `bin/backup.py` (boto3 authentication)
- **Example**: `BACKUP_S3_KEY=AKIAIOSFODNN7EXAMPLE`
- **Security**: IAM user with minimal permissions (PutObject, GetObject)

**`BACKUP_S3_SECRET`** (required for backups)
- **Purpose**: AWS secret access key
- **Used by**: `bin/backup.py` (boto3 authentication)
- **Example**: `BACKUP_S3_SECRET=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY`
- **Security**: Never log or expose, rotate regularly

**`BACKUP_S3_REGION`** (optional, default: us-east-1)
- **Purpose**: AWS region for S3 bucket
- **Used by**: `bin/backup.py`
- **Example**: `BACKUP_S3_REGION=us-west-2`

### Monitoring Configuration

**From `secrets/itsup.txt`**:

**`MONITOR_MODE`** (optional, default: protection)
- **Purpose**: Monitor operating mode
- **Used by**: Container security monitor
- **Values**: `protection`, `report-only`
- **Example**: `MONITOR_MODE=protection`

**`OPENSNITCH_DB_PATH`** (optional, default: /var/lib/opensnitch/opensnitch.sqlite3)
- **Purpose**: Path to OpenSnitch database
- **Used by**: Container security monitor (DNS correlation)
- **Example**: `OPENSNITCH_DB_PATH=/var/lib/opensnitch/opensnitch.sqlite3`
- **Security**: READ-ONLY access, never modify

## Project Variables

### Common Patterns

**From `secrets/{project}.txt`**:

**Database Configuration**:
```bash
DB_HOST=postgres
DB_PORT=5432
DB_NAME=myapp
DB_USER=myapp
DB_PASSWORD=secretpass
DATABASE_URL=postgres://${DB_USER}:${DB_PASSWORD}@${DB_HOST}:${DB_PORT}/${DB_NAME}
```

**Application Configuration**:
```bash
NODE_ENV=production
PORT=3000
LOG_LEVEL=info
```

**Authentication**:
```bash
JWT_SECRET=$(openssl rand -hex 32)
SESSION_SECRET=$(openssl rand -hex 32)
API_KEY=abc123xyz
```

**Email/SMTP**:
```bash
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USER=user@example.com
SMTP_PASS=emailpass
SMTP_FROM=noreply@example.com
```

**External Services**:
```bash
STRIPE_API_KEY=sk_live_...
SENDGRID_API_KEY=SG....
SENTRY_DSN=https://...@sentry.io/...
```

### Docker Compose Usage

**In `projects/{project}/docker-compose.yml`**:
```yaml
services:
  app:
    environment:
      # Simple reference
      - DB_PASSWORD=${DB_PASSWORD}

      # With default value
      - LOG_LEVEL=${LOG_LEVEL:-info}

      # Computed value
      - DATABASE_URL=postgres://${DB_USER}:${DB_PASSWORD}@${DB_HOST}:5432/${DB_NAME}

      # List (multiple vars)
      - ALLOWED_HOSTS=${HOST1},${HOST2}
```

### Loading (mutually exclusive contexts)

Secrets are **not merged across files**. `load_secrets` in `lib/data.py` loads exactly one file depending on context:

- **Infrastructure context** (DNS/proxy/API, `load_secrets()` with no project): loads **ONLY** `secrets/itsup.{enc.txt|txt}`.
- **Project context** (`load_secrets("{project}")`, used by `itsup apply <project>` / `itsup svc`): loads **ONLY** `secrets/{project}.{enc.txt|txt}`.

A project does **NOT** inherit values from `secrets/itsup.txt`. If a project needs a value that also lives in the infra secrets, duplicate it into the project's own secrets file.

**Per-file detection** (each file, encrypted-first):
1. `secrets/{name}.enc.txt` (SOPS-encrypted — production)
2. fallback to `secrets/{name}.txt` (plaintext — development, gitignored)

The combined deploy environment is `{**os.environ, **secrets}` (secrets override the inherited process environment), built by `get_env_with_secrets` in `lib/data.py`.

## CLI Environment Variables

The `itsup` CLI does **not** read configuration from environment variables for verbosity or directory overrides. Verbosity is controlled only by the `-v`/`-vv` count flags (`bin/itsup` explicitly ignores `LOG_LEVEL`). The `projects/`, `secrets/`, and `upstream/` directories are hard-coded relative to the repo root — there are no `ITSUP_CONFIG_DIR`, `ITSUP_SECRETS_DIR`, or `ITSUP_UPSTREAM_DIR` overrides.

## System Environment Variables

**Used by Docker, systemd, or system**:

**`DOCKER_HOST`** (optional, default: unix:///var/run/docker.sock)
- **Purpose**: Docker daemon socket
- **Example**: `export DOCKER_HOST=tcp://localhost:2375`
- **Use case**: Remote Docker daemon

**`COMPOSE_PROJECT_NAME`** (optional, default: directory name)
- **Purpose**: Docker Compose project name prefix
- **Example**: `export COMPOSE_PROJECT_NAME=itsup`
- **Effect**: Containers named `{project}-{service}-{number}`

**`PATH`** (system variable)
- **Purpose**: Executable search path
- **Example**: `export PATH=$PATH:/home/youruser/srv/bin`
- **Use case**: Access `itsup` command without `./` or full path

## Variable Expansion

### Docker Compose Expansion

**At deployment time**, Docker Compose expands `${VAR}` placeholders:

**Input** (`docker-compose.yml`):
```yaml
services:
  app:
    image: myapp:${VERSION}
    environment:
      - DATABASE_URL=${DATABASE_URL}
```

**Environment** (at `docker compose up`):
```bash
VERSION=v1.2.3
DATABASE_URL=postgres://user:pass@host:5432/db
```

**Result** (running container):
```yaml
services:
  app:
    image: myapp:v1.2.3
    environment:
      - DATABASE_URL=postgres://user:pass@host:5432/db
```

### Shell Expansion

**In secrets files**, you can use shell-style variable references:

**secrets/my-app.txt**:
```bash
DB_HOST=postgres
DB_USER=myapp
DB_PASS=secretpass
# Reference other vars (expanded by shell, not Docker Compose)
DATABASE_URL=postgres://${DB_USER}:${DB_PASS}@${DB_HOST}:5432/myapp
```

**Important**: Shell expansion happens in secrets file, Docker Compose expansion happens in compose file.

### Default Values

**Syntax**: `${VAR:-default}`

**Example**:
```yaml
environment:
  - LOG_LEVEL=${LOG_LEVEL:-info}  # Defaults to 'info' if LOG_LEVEL not set
  - PORT=${PORT:-3000}             # Defaults to 3000
```

**Use case**: Optional configuration with sensible defaults.

## Security Best Practices

### Secret Generation

**Use cryptographically secure random**:
```bash
# 32-byte hex (64 characters)
openssl rand -hex 32

# 32-byte base64 (44 characters)
openssl rand -base64 32

# UUID
uuidgen
```

**Store in secrets file**:
```bash
# secrets/itsup.txt
API_SECRET_KEY=$(openssl rand -hex 32)
```

### Secret Storage

**Never**:
- ❌ Commit plaintext secrets to git
- ❌ Hard-code secrets in docker-compose.yml
- ❌ Log secrets (even in debug mode)
- ❌ Store secrets in environment permanently

**Always**:
- ✅ Use `secrets/*.enc.txt` for git storage (encrypted with SOPS)
- ✅ Use `${VAR}` placeholders in compose files
- ✅ Load secrets at deployment time only
- ✅ Use `.gitignore` for plaintext `.txt` files

### Secret Rotation

**Procedure**:
1. Generate new secret value
2. Update secrets file: `vim secrets/{project}.txt`
3. Encrypt: `itsup encrypt {project}`
4. Commit: `git add secrets/{project}.enc.txt && git commit`
5. Deploy: `itsup apply {project}` (loads new secrets)
6. Verify: Check service logs for successful startup

**Frequency**:
- **Critical secrets** (admin tokens): Every 90 days
- **API keys**: When compromised or yearly
- **Database passwords**: When team member leaves or yearly

## Variable Validation

### Required vs Optional

**Required**:
- `TRAEFIK_ADMIN` (in `secrets/itsup.txt` — proxy artifact generation fails without it)
- Database credentials (if project uses database)
- External service API keys (if project uses services)

**Optional** (has defaults or not needed):
- `LOG_LEVEL` (defaults to `info`)
- `PORT` (defaults to service-specific default)

### Validation Methods

**At artifact generation**: `expand_env_vars` in `lib/data.py` raises `ValueError` listing any `${VAR}` that has no matching secret when expanding config templates.

`get_env_with_secrets` itself performs **no** required-var validation — it simply merges loaded secrets over the process environment:
```python
# lib/data.py
def get_env_with_secrets(project_name: str | None = None) -> dict[str, str]:
    secrets = load_secrets(project_name)
    return {**os.environ, **secrets}
```

**Manual validation**:
```bash
# Check if var is set
echo ${ROUTER_IP?Error: ROUTER_IP not set}

# Check if file exists
test -f secrets/itsup.txt || echo "Error: secrets/itsup.txt not found"
```

## Troubleshooting

### Variable Not Expanding

**Symptom**: Container has literal `${VAR}` instead of value.

**Causes**:
1. Secrets not loaded at deployment
2. Wrong variable name
3. Escaping issue

**Fix**:
```bash
# Verify secrets file
cat secrets/{project}.txt | grep VAR

# Verify deployment loads secrets
itsup apply {project} --verbose
# Should show: "Loading secrets for {project}"

# Check container environment
docker exec {container} env | grep VAR
```

### Wrong Value in Container

**Symptom**: Container has unexpected value for variable.

**Causes**:
1. Override in project secrets file
2. Hard-coded in compose file
3. Set by parent environment

**Fix**:
```bash
# Check both secrets files
cat secrets/itsup.txt | grep VAR
cat secrets/{project}.txt | grep VAR

# Check compose file for hard-coded values
grep VAR projects/{project}/docker-compose.yml

# Check what itsup loads
itsup apply {project} --verbose | grep VAR
```

### Secret Not Decrypting

**Symptom**: `itsup decrypt` fails or empty file.

**Causes**:
1. Missing SOPS keys
2. Corrupted encrypted file
3. Wrong encryption method

**Fix**:
```bash
# Verify encrypted file exists and has content
ls -lh secrets/{project}.enc.txt

# Check SOPS configuration
cat .sops.yaml

# Try manual decryption
sops -d secrets/{project}.enc.txt

# If all fails, restore from git
git checkout HEAD -- secrets/{project}.enc.txt
itsup decrypt {project}
```

## Environment File Templates

### Infrastructure Secrets Template

**`secrets/itsup.txt`**:
```bash
# Traefik dashboard / admin basic-auth (htpasswd line; REQUIRED for proxy artifacts)
TRAEFIK_ADMIN=admin:$apr1$changeme

# API Configuration
API_SECRET_KEY=changeme
API_ADMIN_TOKEN=changeme

# Backup Configuration
BACKUP_S3_BUCKET=my-backup-bucket
BACKUP_S3_KEY=changeme
BACKUP_S3_SECRET=changeme
BACKUP_S3_REGION=us-east-1

# Monitoring
MONITOR_MODE=protection
OPENSNITCH_DB_PATH=/var/lib/opensnitch/opensnitch.sqlite3
```

### Project Secrets Template

**`secrets/{project}.txt`**:
```bash
# Application
NODE_ENV=production
PORT=3000
LOG_LEVEL=info

# Database
DB_HOST=postgres
DB_PORT=5432
DB_NAME=myapp
DB_USER=myapp
DB_PASSWORD=changeme

# Authentication
JWT_SECRET=changeme
SESSION_SECRET=changeme

# External Services
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USER=user@example.com
SMTP_PASS=changeme
SMTP_FROM=noreply@example.com

# API Keys
STRIPE_API_KEY=changeme
SENDGRID_API_KEY=changeme
```

## Future Improvements

- **Secret validation**: Schema-based validation of required secrets
- **Secret rotation tools**: Automated secret rotation scripts
- **Secret providers**: Integration with HashiCorp Vault, AWS Secrets Manager
- **Environment profiles**: Different secret sets for dev/staging/prod
- **Secret scanning**: Pre-commit hooks to prevent secret leaks
