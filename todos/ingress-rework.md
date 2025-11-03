# Ingress/Egress Rework & Config File Rename

## 🎯 Goals
1. **Network Segmentation**: Implement egress-based network policies to prevent lateral movement between projects
2. **Config Clarity**: Rename `ingress.yml` → `itsup-project.yml` (file contains more than just ingress)
3. **Security**: Minimize attack surface by restricting inter-container communication to declared dependencies

## 🔒 Security Problem (Current State)
- All services on shared `proxynet` = compromised container can sniff/attack any service
- No network-level isolation between projects
- `encrypted: 'true'` flag does nothing in Docker Compose (Swarm-only feature)

## ✅ Design Decisions
- **Egress format**: Docker Compose service names (e.g., `ai-assistant-web`, `n8n-api`)
- **Schema**: New `Egress` model (similar to `Ingress` but simpler - no domain field)
- **Proxynet assignment**: ONLY services with ingress declarations (Traefik access)
- **Default isolation**: Services without ingress/egress stay on project-local `default` network
- **Migration**: Support both filenames temporarily (v2.x) with deprecation warning

## 📋 Implementation Phases

### Phase 1: Schema Enhancement
**Files to modify:**
- `lib/models.py` - Add `Egress` class + `egress` field to `TraefikConfig`

**Tasks:**
1. Create `Egress` class with fields:
   - `service: str` - Target service name (format: `{project}-{service}`)
   - `port: int | None` - Optional port override
   - `protocol: Protocol = tcp` - Protocol (reuse existing enum)

2. Add `egress: List[Egress] = []` to `TraefikConfig` class

3. Update `load_project()` in `lib/data.py`:
   - Parse egress declarations from YAML
   - Validate egress service names (check target project exists)

4. Validation logic:
   - Check egress target project exists in `projects/`
   - Check target service exists in target project's docker-compose.yml
   - Warn if egress target has no matching service

**Example schema:**
```yaml
# itsup-project.yml (or ingress.yml during migration)
enabled: true
ingress:
  - service: web
    domain: example.com
    port: 3000
egress:
  - service: n8n-api        # Can call n8n-api in n8n project
    port: 5678
  - service: minio-api      # Can call minio-api in minio project
```

### Phase 2: Network Segmentation Logic
**Files to modify:**
- `bin/write_artifacts.py` - Rewrite network assignment in `write_upstream()`

**Current behavior (lines 177-196):**
```python
# ALL services get proxynet
for service_name, service_config in services.items():
    service_config["networks"].append("proxynet")
```

**New behavior:**
```python
# 1. Services with INGRESS → add proxynet (Traefik needs access)
# 2. Services with EGRESS → add target project networks
# 3. Services with NEITHER → stay on default only

for service_name, service_config in services.items():
    labels = service_config.get("labels", [])
    has_traefik = any("traefik.enable=true" in str(label) for label in labels)

    # Add proxynet ONLY if service has ingress
    if has_traefik:
        service_config["networks"].append("proxynet")

    # Add target networks for egress declarations
    for egress in traefik_config.egress:
        target_project = egress.service.split('-')[0]  # Extract project from service name
        target_network = f"{target_project}_default"

        if target_network not in compose["networks"]:
            compose["networks"][target_network] = {"external": True}

        if target_network not in service_config["networks"]:
            service_config["networks"].append(target_network)
```

**Tasks:**
1. Remove blanket proxynet assignment
2. Add conditional proxynet (only if has Traefik labels)
3. Parse egress declarations and add target networks
4. Add target project networks to compose["networks"] section
5. Handle edge cases:
   - Service with ingress + egress (gets both proxynet + target networks)
   - Service with neither (stays on default only)
   - Invalid egress targets (log warning, skip)

### Phase 3: Config File Rename (Breaking Change)
**Migration strategy:** Accept both filenames during v2.x with deprecation warning

**Files to modify:**
1. `lib/data.py:168` - Main loading logic
2. `lib/data.py:193` - Project detection
3. `commands/init.py:130,276` - Help text
4. `bin/migrate_to_v2.py:481` - Migration script
5. `samples/projects/example-project/` - Rename sample file
6. All test files (6+ files)
7. All documentation files

**Implementation:**
```python
# lib/data.py - load_project()
def load_traefik_config(project_name: str) -> TraefikConfig:
    """Load itsup-project.yml (or ingress.yml for backward compatibility)"""
    project_dir = Path("projects") / project_name

    # Try new filename first
    new_file = project_dir / "itsup-project.yml"
    old_file = project_dir / "ingress.yml"

    if new_file.exists():
        config_file = new_file
    elif old_file.exists():
        config_file = old_file
        logger.warning(
            f"⚠️  {project_name}/ingress.yml is deprecated. "
            f"Rename to itsup-project.yml (support ends in v3.0)"
        )
    else:
        # Return disabled project (no config file)
        return TraefikConfig(enabled=False)

    # Load and parse...
```

**Migration command (future):**
```bash
# Add to bin/migrate_to_v2.py or create new command
itsup migrate rename-configs  # Rename all ingress.yml → itsup-project.yml
```

**Deprecation timeline:**
- v2.x: Accept both names, warn on old name
- v3.0: Remove support for `ingress.yml`

### Phase 4: Bug Fixes
**Files to modify:**
- `bin/write_artifacts_test.py:12` - Fix non-existent `IngressV2` import

**Current code:**
```python
from lib.models import IngressV2  # DOES NOT EXIST
```

**Fix:**
```python
from lib.models import Ingress  # Correct class name
```

**Additional:**
- Remove or implement unused `expose` field in Ingress model
- Clarify its purpose in documentation or remove entirely

### Phase 5: Testing & Documentation

**New tests needed:**
1. Egress validation:
   - Valid egress targets
   - Invalid project names
   - Invalid service names
   - Circular dependencies

2. Network assignment:
   - Service with ingress only → proxynet
   - Service with egress only → target networks
   - Service with both → proxynet + target networks
   - Service with neither → default only

3. Config file loading:
   - Load itsup-project.yml
   - Fall back to ingress.yml with warning
   - Handle missing config (disabled project)

**Documentation updates:**
- README.md - Update config file references
- CLAUDE.md - Update file paths
- docs/ - Update all examples to use itsup-project.yml
- samples/ - Rename sample files
- Inline comments explaining egress semantics

**Example documentation:**
```yaml
# itsup-project.yml - Project configuration for itsUP

enabled: true  # Set to false to disable project

# Ingress: Services exposed via Traefik (external access)
ingress:
  - service: web          # Service from docker-compose.yml
    domain: example.com   # Domain for TLS termination
    port: 3000           # Service port

# Egress: Services this project needs to call (cross-project access)
egress:
  - service: n8n-api           # Target: n8n project, n8n-api service
  - service: minio-api         # Target: minio project, minio-api service
```

## 🚨 Breaking Changes

1. **Network assignment change:**
   - Services without ingress NO LONGER get proxynet by default
   - Must declare egress to access other projects
   - May break existing inter-project communication

2. **Config file rename:**
   - `ingress.yml` deprecated (v2.x grace period)
   - Will be removed in v3.0

3. **DNS resolution:**
   - Services on different networks may not resolve each other
   - Egress declarations required for cross-project DNS

## 🔄 Migration Path

**For existing projects:**
1. Audit inter-project communication (logs, DNS queries)
2. Add egress declarations for cross-project calls
3. Rename ingress.yml → itsup-project.yml (optional in v2.x)
4. Test with `itsup apply <project>`
5. Monitor for resolution failures

**Detection of missing egress:**
- DNS honeypot logs will show NXDOMAIN for missing egress
- Application errors (connection refused, name not found)

**Example migration:**
```yaml
# Before (implicit access via proxynet)
enabled: true
ingress:
  - service: web
    domain: example.com
    port: 3000

# After (explicit egress declarations)
enabled: true
ingress:
  - service: web
    domain: example.com
    port: 3000
egress:
  - service: n8n-api      # Explicitly allow calling n8n-api
  - service: minio-api    # Explicitly allow calling minio-api
```

## 📝 Implementation Checklist

### Schema (lib/models.py)
- [ ] Create `Egress` class with service, port, protocol fields
- [ ] Add `egress: List[Egress]` to `TraefikConfig`
- [ ] Update `__init__` and defaults

### Loading (lib/data.py)
- [ ] Support both `itsup-project.yml` and `ingress.yml`
- [ ] Add deprecation warning for `ingress.yml`
- [ ] Parse egress declarations
- [ ] Validate egress targets (project + service exist)

### Network Assignment (bin/write_artifacts.py)
- [ ] Remove blanket proxynet assignment
- [ ] Add conditional proxynet (only if has Traefik labels)
- [ ] Parse egress and add target project networks
- [ ] Update compose["networks"] with target networks

### Bug Fixes
- [ ] Fix `IngressV2` import in test file
- [ ] Remove or implement `expose` field

### File Renames
- [ ] Update all "ingress.yml" string literals
- [ ] Rename sample files
- [ ] Update init command help text
- [ ] Update migration script

### Tests
- [ ] Egress validation tests
- [ ] Network assignment tests
- [ ] Config file loading tests (both names)
- [ ] Update existing tests for new behavior

### Documentation
- [ ] README.md examples
- [ ] CLAUDE.md file path references
- [ ] Inline code comments
- [ ] Migration guide
- [ ] Deprecation timeline

## 🤔 Open Questions

1. **Egress service name format:**
   - Current: `n8n-api` (assumes project name matches compose service prefix)
   - Should we support `project:service` syntax for clarity?
   - What if project name != compose service prefix?

2. **DNS resolution with egress:**
   - Docker DNS only works for networks you're on
   - Egress to `n8n-api` → join `n8n_default` network → can resolve ALL n8n services
   - Is this acceptable or do we need service-level DNS filtering?

3. **Circular dependencies:**
   - Project A egress → B, Project B egress → A
   - Should we detect/warn about circular dependencies?

4. **Default egress policies:**
   - Should some services (monitoring, logging) get automatic egress to all?
   - Or always require explicit declaration?

5. **Proxynet security:**
   - Even with minimal proxynet, Traefik can reach all ingress services
   - Is this acceptable or should we segment Traefik per project?

## 📚 References

- Current schema: `lib/models.py:71-107` (Ingress class)
- Network assignment: `bin/write_artifacts.py:177-196`
- Config loading: `lib/data.py:168`
- Kubernetes NetworkPolicy docs (inspiration)
