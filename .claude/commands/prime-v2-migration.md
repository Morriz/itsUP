# Prime Context: V2 Migration

You are working on **V2 migration** - completing the migration from db.yml-based V1 to projects/-based V2 architecture.

## V2 Architecture (Target State)

**Key Changes from V1:**
1. **No more db.yml** - Configuration split into individual project directories
2. **projects/** structure - Each project has its own `docker-compose.yml` and `ingress.yml`
3. **Artifact generation** - Templates generate proxy and upstream configs from projects/
4. **User overrides** - `projects/traefik.yml` merged on top of generated `proxy/traefik/traefik.yml`

## Current Migration Status

**Completed:**
- ✅ V2 data loading functions in `lib/data.py`
- ✅ Project structure in `projects/{name}/docker-compose.yml` + `traefik.yml`
- ✅ Upstream artifact generation in `bin/write_artifacts.py`
- ✅ Stack-based CLI commands (dns, proxy, svc, run)
- ✅ V1 API code removed from V2 branch

**In Progress:**
- ⏳ Proxy artifact generation - needs .env config instead of db.yml functions
- ⏳ Migration script to convert db.yml → projects/ structure (do this LAST)

**What Works:**
- ✅ `inject_traefik_labels()` - Reads ingress.yml, generates Traefik labels
- ✅ `write_upstream()` - Generates upstream/{project}/docker-compose.yml
- ✅ V2 models: `IngressV2`, `TraefikConfig`
- ✅ `load_project()` - Loads docker-compose.yml + ingress.yml

**What's Missing:**
- Proxy generation functions don't exist yet (need to be added)
- Functions like `get_plugin_registry()`, `get_projects()`, `get_versions()` removed with V1
- For V2, use .env for infrastructure config until db.yml migration is done

## Critical Files to Read

**Start with these to understand V2:**

1. **README.md** - Updated with V2 CLI commands and architecture
2. **CLAUDE.md** - Developer guide with V2 patterns
3. **lib/data.py** - V2 data loading (projects/ based, NO db.yml)
4. **lib/models.py** - Pydantic models (TraefikConfig for V2)
5. **bin/write_artifacts.py** - Artifact generation (currently incomplete for proxy)
6. **commands/run.py** - Orchestrated startup (dns→proxy→api→monitor)

**Templates (V2 compatible):**
- `tpl/proxy/docker-compose.yml.j2` - Proxy stack template
- `tpl/proxy/traefik.yml.j2` - Traefik config template
- `tpl/proxy/routers-{http,tcp,udp}.yml.j2` - Dynamic routing templates
- `tpl/upstream/docker-compose.yml.j2` - Upstream service template

**Sample configs:**
- `samples/traefik.yml` - User override template (native Traefik YAML schema)
- `samples/example-project/` - Example project structure

## V2 Data Flow

```
projects/
├── {project}/
│   ├── docker-compose.yml    # Service definitions
│   └── ingress.yml            # Ingress/routing config (IngressV2 model)
└── traefik.yml                # Infrastructure overrides (copied from samples/)

↓ bin/write_artifacts.py

1. Per-project artifact generation:
   - load_project(name) → (compose_dict, TraefikConfig)
   - inject_traefik_labels(compose, ingress_config, name)
   - Write to upstream/{project}/docker-compose.yml (with Traefik labels)

2. Proxy artifact generation:
   - Generate proxy/docker-compose.yml from tpl/proxy/docker-compose.yml.j2
   - Generate proxy/traefik/traefik.yml from tpl + merge projects/traefik.yml overrides
   - Generate proxy/traefik/dynamic/routers-*.yml from tpl

Generated structure:
├── proxy/
│   ├── docker-compose.yml     # Traefik stack
│   └── traefik/
│       ├── traefik.yml        # Static config with user overrides merged
│       └── dynamic/
│           ├── routers-http.yml   # Static routers for hostport/passthrough
│           ├── routers-tcp.yml
│           └── routers-udp.yml
└── upstream/{project}/
    └── docker-compose.yml     # With Traefik labels injected for dynamic discovery
```

## V2 Label Injection (Already Implemented!)

The `inject_traefik_labels()` function in `bin/write_artifacts.py` reads `ingress.yml` and generates Traefik labels:

**HTTP routing:**
```yaml
# ingress.yml
ingress:
  - service: web
    domain: example.com
    port: 80
    router: http

# Generates labels:
traefik.enable=true
traefik.http.routers.myproject-web.entrypoints=websecure
traefik.http.routers.myproject-web.rule=Host(`example.com`)
traefik.http.routers.myproject-web.tls=true
traefik.http.routers.myproject-web.tls.certresolver=letsencrypt
traefik.http.services.myproject-web.loadbalancer.server.port=80
```

**TCP/UDP routing:**
- Similar pattern for TCP/UDP with hostport support
- Passthrough mode for TLS passthrough

## Key Questions for V2 Proxy Generation

**Where should infrastructure config live?**
- Plugins (CrowdSec enabled/version/apikey)?
- Versions (traefik, crowdsec versions)?
- Trusted IPs (for entryPoints)?
- Let's Encrypt email/staging?

**Options:**
1. Environment variables (.env)
2. projects/traefik.yml (infrastructure overrides)
3. New file like projects/infrastructure.yml
4. Hardcoded defaults with override capability

**Current approach (for testing):**
Use .env for infrastructure config until db.yml migration is complete.

## Testing Strategy

**Phase 1: Test V2 without db.yml data**
1. Use minimal .env config for proxy generation
2. Create sample project in projects/
3. Run `bin/write_artifacts.py` to generate all artifacts
4. Run `itsup run` to start full stack
5. Verify DNS, proxy, monitor all work

**Phase 2: Migrate db.yml data**
1. Read db.yml structure
2. Create projects/ structure for each project
3. Move plugin config to appropriate location
4. Test migration script
5. Delete db.yml

## Environment Variables Needed (.env)

For V2 proxy generation (minimal set):
```bash
# Let's Encrypt
LETSENCRYPT_EMAIL=admin@example.com
LETSENCRYPT_STAGING=false

# Network
DOMAIN_SUFFIX=example.com
TRUSTED_IPS_CIDRS=127.0.0.1/32,192.168.1.1/32

# Traefik
TRAEFIK_DOMAIN=traefik.example.com
TRAEFIK_ADMIN=admin:htpasswd_hash

# CrowdSec (optional)
CROWDSEC_ENABLED=false
CROWDSEC_VERSION=v1.6.8
CROWDSEC_API_KEY=

# Versions
TRAEFIK_VERSION=v3.2
```

## Ready to Work

You are now primed for V2 migration work. Key priorities:

1. **Complete proxy artifact generation** - Use .env for config data
2. **Test V2 setup works** - Full stack startup without db.yml
3. **Then migrate db.yml** - Only after V2 proven working

Read the files above, understand V2 data flow, then proceed with completing proxy generation using .env config.
