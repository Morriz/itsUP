# Prime Context: Proxy Infrastructure (V2)

You are now working on the **proxy infrastructure** for this system.

## Architecture Overview

This system uses a **Traefik label-based routing** paradigm (V2):

1. **Source of Truth**: Project compose files in `projects/{project}/docker-compose.yml` and `projects/{project}/traefik.yml`
2. **Code Generation**: Python scripts generate:
   - `upstream/{project}/docker-compose.yml` - Service configuration with Traefik labels injected
3. **Routing**:
   - Traefik automatically discovers services via Docker labels
   - No separate proxy configuration files needed

## Key Components

### Routing Modes
- **HTTP/HTTPS**: Domain-based routing with automatic TLS via Let's Encrypt
- **TCP**: SNI-based routing for raw TCP (databases, VPN)
- **UDP**: Port-based routing (VPN)

### Discovery Method (V2)
All services use **Traefik Docker Labels** which are automatically injected into docker-compose files during generation.

## Critical Files to Read

**Start here** to understand the V2 system:

1. **bin/write_artifacts.py** - Generate upstream configs with Traefik labels
   - `inject_traefik_labels()` - Injects Traefik labels into services
   - `write_upstream()` - Generates single project config
   - `write_upstreams()` - Generates all project configs

2. **lib/data.py** - Project loading and validation
   - `load_project()` - Loads docker-compose.yml and traefik.yml from projects/
   - `validate_all()` - Validates all projects

3. **README.md** - Project documentation
   - V2 Architecture section

## Key Concepts (V2)

### Update Flow
```
projects/{project}/docker-compose.yml change → itsup apply → write_upstreams() → docker compose up -d
```

### Label Injection
Traefik labels are automatically injected based on the `ingress` section in `projects/{project}/traefik.yml`.

## Common Tasks

**Regenerate upstream configs**:
```bash
python3 bin/write_artifacts.py  # Generates all upstream configs
```

**Apply changes**:
```bash
itsup apply                  # Deploy all projects
itsup apply <project>        # Deploy single project
```

**Debug routing**:
- `docker logs <project>-<service>` to see Traefik label discovery
- Check generated `upstream/{project}/docker-compose.yml` for injected labels

## Important Constraints

1. **Never modify generated files directly** - Always edit source files in `projects/{project}/`
2. **Validate YAML** after changes with `docker compose config --quiet` in the upstream directory

## Ready to Work

You are now primed to work on the proxy infrastructure. Read the files above in order, then ask any questions about the specific task.
