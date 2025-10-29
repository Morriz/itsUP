# Deployment Operations

Deployment procedures and strategies for itsup infrastructure.

## Overview

**Deployment Philosophy**: Zero-downtime deployments with smart change detection.

**Key Features**:
- Configuration-driven (YAML)
- Smart rollout (only deploys when config changed)
- Parallel deployment (multiple projects at once)
- Health check integration
- Automatic artifact generation

## Deployment Flow

```
User Change → itsup apply → Config Hash → Changed? → Generate Artifacts → Docker Compose Up
                                  ↓
                                 No → Skip (already deployed)
```

### Change Detection

**How it works**:
1. Calculate MD5 hash of project configuration (`docker-compose.yml` + `ingress.yml`)
2. Compare with hash stored in running container labels
3. If different: Deploy
4. If same: Skip

**Benefits**:
- Avoids unnecessary container restarts
- Faster operations (no-op for unchanged projects)
- Clear feedback (shows which projects deployed)

### Smart Rollout

**Strategy**: Docker Compose `up` with scale-based blue-green deployment.

**For multi-container services**:
1. Start new container(s) with updated config
2. Wait for health checks to pass
3. Stop old container(s)
4. Remove old container(s)

**For single-container services**:
1. Stop old container
2. Start new container with updated config

**Zero-downtime**: Traefik automatically routes to healthy containers.

## Deployment Commands

### Full Infrastructure Deployment

```bash
itsup run
```

**What it does**:
1. Start DNS stack (creates `proxynet` network)
2. Start Proxy stack (Traefik + dockerproxy)
3. Start API (host process)
4. Start Monitor (host process)

**Use case**: Initial setup, full system restart after reboot.

### All Projects Deployment

```bash
itsup apply
```

**What it does**:
1. Load all projects from `projects/` directory
2. Calculate config hash for each
3. For changed projects (in parallel):
   - Regenerate `upstream/{project}/docker-compose.yml`
   - Run `docker compose up -d`
4. Report results (deployed, skipped, failed)

**Use case**: Deploy all changes after configuration updates.

**Output example**:
```
✓ project-a deployed (config changed)
○ project-b skipped (no changes)
✗ project-c failed (docker error)
```

### Single Project Deployment

```bash
itsup apply <project>
```

**What it does**:
1. Load project from `projects/{project}/`
2. Calculate config hash
3. If changed:
   - Regenerate `upstream/{project}/docker-compose.yml`
   - Run `docker compose up -d`
4. Report result

**Use case**: Deploy changes to specific project.

### Service-Specific Operations

```bash
itsup svc <project> up [service]        # Start service(s)
itsup svc <project> down [service]      # Stop service(s)
itsup svc <project> restart [service]   # Restart service(s)
itsup svc <project> pull [service]      # Pull image updates
```

**Use case**: Manual service management without regenerating config.

## Configuration Updates

### Changing Service Configuration

**1. Edit project docker-compose.yml**:
```bash
vim projects/{project}/docker-compose.yml
```

**2. Deploy**:
```bash
itsup apply {project}
```

**What happens**:
- Config hash changes
- Artifacts regenerated
- Containers restarted with new config

### Changing Routing Configuration

**1. Edit ingress.yml**:
```bash
vim projects/{project}/ingress.yml
```

**Example - Add new route**:
```yaml
enabled: true
ingress:
  - service: web
    domain: app.example.com
    port: 3000
    router: http
  - service: api  # NEW
    domain: api.example.com
    port: 8080
    router: http
```

**2. Deploy**:
```bash
itsup apply {project}
```

**What happens**:
- Traefik labels regenerated
- Containers recreated with new labels
- Traefik picks up new routes automatically

### Changing Infrastructure Configuration

**1. Edit itsup.yml**:
```bash
vim projects/itsup.yml
```

**2. Regenerate proxy config**:
```bash
bin/write_artifacts.py  # Regenerates all configs
```

**3. Restart proxy**:
```bash
itsup proxy restart
```

### Changing Traefik Configuration

**1. Edit traefik.yml overrides**:
```bash
vim projects/traefik.yml
```

**Example - Add custom middleware**:
```yaml
http:
  middlewares:
    rate-limit:
      rateLimit:
        average: 100
        burst: 50
```

**2. Regenerate and restart**:
```bash
bin/write_artifacts.py
itsup proxy restart traefik
```

## Deployment Best Practices

### Pre-Deployment Checklist

- [ ] Backup current configuration (`git commit && git push`)
- [ ] Validate configuration (`itsup validate` or `itsup validate {project}`)
- [ ] Review changes (`git diff`)
- [ ] Check secrets are up-to-date (`ls -l secrets/*.enc.txt`)
- [ ] Verify sufficient disk space (`df -h`)
- [ ] Check no containers in error state (`docker ps -a --filter "status=exited"`)

### Deployment Order (Manual Full Deploy)

**Correct order**:
1. DNS stack (`itsup dns up`)
2. Proxy stack (`itsup proxy up`)
3. API (`bin/start-api.sh` or systemd)
4. Monitor (`itsup monitor start` or systemd)
5. Projects (`itsup apply`)

**Why this order**:
- DNS creates `proxynet` network (required by proxy)
- Proxy creates Traefik (required by projects for routing)
- API and Monitor can start anytime after proxy

**Easy way**: `itsup run` (does it all automatically)

### Post-Deployment Verification

**Check infrastructure**:
```bash
docker network ls | grep proxynet      # Network exists
itsup proxy logs traefik | tail -20    # Traefik healthy
curl http://localhost:80/health        # Traefik responding
```

**Check project**:
```bash
itsup svc {project} ps                 # Containers running
itsup svc {project} logs -f            # Check logs for errors
curl https://{domain}/health           # Service responding
```

**Check Traefik routing**:
```bash
# Traefik should log new routes discovered
itsup proxy logs traefik | grep "Adding route"
```

### Rollback Procedures

**Quick rollback** (git-based):
```bash
# Find last known good commit
git log --oneline | head -5

# Rollback to specific commit
git checkout <commit-hash> -- projects/{project}/

# Deploy rollback
itsup apply {project}
```

**Emergency rollback** (stop service):
```bash
# Stop problematic service immediately
itsup svc {project} down

# Or specific service
itsup svc {project} down {service}

# Fix and redeploy when ready
```

## Common Deployment Scenarios

### Scenario 1: New Project Deployment

**Setup**:
```bash
# Create project directory
mkdir -p projects/my-app

# Create docker-compose.yml
cat > projects/my-app/docker-compose.yml <<EOF
services:
  web:
    image: nginx:latest
    volumes:
      - ./html:/usr/share/nginx/html:ro
    networks:
      - proxynet
networks:
  proxynet:
    external: true
EOF

# Create ingress.yml
cat > projects/my-app/ingress.yml <<EOF
enabled: true
ingress:
  - service: web
    domain: my-app.example.com
    port: 80
    router: http
EOF
```

**Deploy**:
```bash
itsup apply my-app
```

**Verify**:
```bash
itsup svc my-app ps
curl https://my-app.example.com
```

### Scenario 2: Image Update (New Version)

**Update docker-compose.yml**:
```bash
vim projects/{project}/docker-compose.yml

# Change:
# image: app:v1.0
# To:
# image: app:v2.0
```

**Deploy**:
```bash
itsup apply {project}
```

**What happens**:
1. Config hash changes (image version changed)
2. `docker compose pull` pulls new image
3. `docker compose up -d` recreates container with new image
4. Old container removed after new one is healthy

### Scenario 3: Adding Service to Existing Project

**Update docker-compose.yml**:
```yaml
services:
  web:
    image: nginx:latest
    # ... existing config

  api:  # NEW SERVICE
    image: node:20-alpine
    command: npm start
    environment:
      - PORT=3000
    networks:
      - proxynet
```

**Update ingress.yml**:
```yaml
ingress:
  - service: web
    domain: app.example.com
    port: 80
    router: http
  - service: api  # NEW ROUTE
    domain: api.example.com
    port: 3000
    router: http
```

**Deploy**:
```bash
itsup apply {project}
```

**Result**: New service starts, new route added to Traefik.

### Scenario 4: Environment Variable Change

**If using secrets file**:
```bash
# Edit secrets file
vim secrets/{project}.txt

# Add/change variable
NEW_VAR=value

# Re-encrypt
itsup encrypt {project}

# Commit
git add secrets/{project}.enc.txt
git commit -m "Update {project} secrets"
```

**If in docker-compose.yml**:
```yaml
services:
  app:
    environment:
      - NEW_VAR=${NEW_VAR}  # Placeholder for secrets file
```

**Deploy**:
```bash
itsup apply {project}
```

**Important**: Secrets are loaded from `secrets/itsup.txt` + `secrets/{project}.txt` at deployment time.

### Scenario 5: Scale Service (Multiple Replicas)

**Update docker-compose.yml**:
```yaml
services:
  web:
    image: nginx:latest
    deploy:
      replicas: 3  # Run 3 instances
    # ... rest of config
```

**Deploy**:
```bash
itsup apply {project}
```

**Or manually scale**:
```bash
docker compose -f upstream/{project}/docker-compose.yml up -d --scale web=3
```

**Result**: Traefik automatically load-balances across all replicas.

## Troubleshooting Deployments

### Deployment Hangs

**Symptom**: `itsup apply` never completes.

**Check**:
```bash
# Look for unhealthy containers
docker ps -a --filter "health=unhealthy"

# Check logs for startup errors
itsup svc {project} logs
```

**Fix**:
```bash
# Stop deployment
Ctrl+C

# Force stop containers
itsup svc {project} down

# Check and fix configuration
vim projects/{project}/docker-compose.yml

# Retry
itsup apply {project}
```

### Config Not Taking Effect

**Symptom**: Changed config but containers not updating.

**Reason**: Config hash not changing (maybe wrong file edited).

**Check**:
```bash
# Verify you edited projects/, not upstream/
ls -l projects/{project}/docker-compose.yml
ls -l upstream/{project}/docker-compose.yml

# Check current vs running config hash
docker compose -f upstream/{project}/docker-compose.yml config --hash "*"
docker inspect {container} --format '{{index .Config.Labels "com.docker.compose.config-hash"}}'
```

**Fix**:
```bash
# Force deployment by stopping containers (removes hash labels)
itsup svc {project} down

# Deploy again
itsup apply {project}
```

### Secrets Not Loading

**Symptom**: Container starts but environment variables are empty or wrong.

**Check**:
```bash
# Verify secrets file exists and is decrypted
cat secrets/{project}.txt

# Check encryption
itsup decrypt {project}
```

**Fix**:
```bash
# If .txt is empty but .enc.txt exists
itsup decrypt {project}

# Deploy again (ensure secrets are loaded)
itsup apply {project}
```

### Network Issues After Deploy

**Symptom**: Container can't reach other containers or internet.

**Check**:
```bash
# Verify proxynet network exists
docker network ls | grep proxynet

# Verify container is connected
docker inspect {container} | grep -A 10 Networks
```

**Fix**:
```bash
# Recreate network (if missing)
itsup dns down
itsup dns up

# Reconnect container
itsup svc {project} restart
```

### Health Check Failures

**Symptom**: Traefik not routing to service, health checks failing.

**Check**:
```bash
# View container health status
docker ps --filter "name={project}"

# Check health check logs
docker inspect {container} | jq '.[0].State.Health'
```

**Fix**:
```bash
# Review health check configuration
vim projects/{project}/docker-compose.yml

# Adjust health check:
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost/health"]
  interval: 10s
  timeout: 5s
  retries: 3
  start_period: 30s  # Increase if service is slow to start
```

### Image Pull Failures

**Symptom**: Deployment fails with "image not found" or "pull access denied".

**Check**:
```bash
# Try pulling manually
docker pull {image}:{tag}

# Check registry authentication
docker login {registry}
```

**Fix**:
```bash
# For private registries, add credentials
docker login ghcr.io -u username -p token

# Or configure in docker-compose.yml
services:
  app:
    image: ghcr.io/user/app:latest
    environment:
      - DOCKER_AUTH_CONFIG={"auths": {...}}
```

## Monitoring Deployments

### Deployment Logs

**Watch deployment progress**:
```bash
# Via CLI
itsup apply {project} --verbose

# Via logs
tail -f logs/api.log | grep -i deploy
```

### Container Health

**Check all containers**:
```bash
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

**Check specific project**:
```bash
itsup svc {project} ps
```

### Traefik Route Discovery

**Watch Traefik discover new routes**:
```bash
itsup proxy logs traefik | grep -E "(Adding route|Register|Configuration)"
```

### Resource Usage

**Check resource consumption**:
```bash
docker stats --no-stream
# Shows CPU, memory, network for all containers
```

## Advanced Deployment Topics

### Blue-Green Deployments

**For critical services**, use explicit blue-green strategy:

```yaml
# docker-compose.yml
services:
  web-blue:
    image: app:v1
    labels:
      - traefik.http.services.web.loadbalancer.server.port=3000
    networks:
      - proxynet

  web-green:
    image: app:v2
    labels:
      - traefik.http.services.web.loadbalancer.server.port=3000
    networks:
      - proxynet
    # Initially scale=0
```

**Deploy**:
```bash
# Start green
docker compose up -d --scale web-green=1

# Test green
curl https://app.example.com  # Should hit green

# Switch traffic (Traefik automatically load-balances)
docker compose up -d --scale web-blue=0

# Cleanup
docker compose rm -f web-blue
```

### Canary Deployments

**Use Traefik weights** for gradual rollout:

```yaml
# ingress.yml with custom labels
labels:
  - traefik.http.services.web-v1.loadbalancer.server.port=3000
  - traefik.http.services.web-v1.loadbalancer.weight=90
  - traefik.http.services.web-v2.loadbalancer.server.port=3000
  - traefik.http.services.web-v2.loadbalancer.weight=10
  - traefik.http.routers.web.service=web-weighted
  - traefik.http.services.web-weighted.weighted.services[0].name=web-v1
  - traefik.http.services.web-weighted.weighted.services[0].weight=90
  - traefik.http.services.web-weighted.weighted.services[1].name=web-v2
  - traefik.http.services.web-weighted.weighted.services[1].weight=10
```

**Gradually shift traffic**: Change weights over time (90/10 → 50/50 → 10/90 → 0/100).

### Database Migrations

**For services with databases**, coordinate migrations with deployments:

```yaml
# docker-compose.yml
services:
  migrate:
    image: app:v2
    command: npm run migrate
    # Run once, then exit
    restart: "no"
    depends_on:
      - db

  app:
    image: app:v2
    depends_on:
      migrate:
        condition: service_completed_successfully
```

**Deploy**:
```bash
itsup apply {project}
# Migrations run first, then app starts
```

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Deploy
on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Deploy via SSH
        uses: appleboy/ssh-action@master
        with:
          host: ${{ secrets.SERVER_IP }}
          username: morriz
          key: ${{ secrets.SSH_KEY }}
          script: |
            cd /home/morriz/srv
            git pull
            source env.sh
            itsup apply
```

### Pre-Commit Hooks

**Validate before commit**:

```bash
# .git/hooks/pre-commit
#!/bin/bash
source env.sh
itsup validate
if [ $? -ne 0 ]; then
  echo "Validation failed!"
  exit 1
fi
```

## Future Improvements

- **Deployment History**: Track all deployments with timestamps and outcomes
- **Automatic Rollback**: Auto-rollback on health check failures
- **Deployment Locking**: Prevent concurrent deployments
- **Progressive Delivery**: Automated canary analysis with metrics
- **Change Impact Analysis**: Predict which services will be affected by config changes
- **Deployment Approval**: Require manual approval for production deployments
