# Networking

itsUP uses a hybrid networking approach combining Docker bridge networks and host networking for optimal performance and zero-downtime deployments.

## Network Topology

```
┌─────────────────────────────────────────────────────────────────┐
│                        Physical Network                          │
│                      192.168.1.0/24 (LAN)                       │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                  ┌───────▼────────┐
                  │  itsUP Host    │
                  │  192.168.1.X   │
                  └────────────────┘
                          │
        ┌─────────────────┼─────────────────┐
        │                 │                 │
   ┌────▼─────┐      ┌────▼─────┐     ┌────▼────┐
   │   Host   │      │ proxynet │     │ Project │
   │ Network  │      │ Bridge   │     │ Networks│
   │          │      │172.20/16 │     │ (user)  │
   └──────────┘      └──────────┘     └─────────┘
        │                 │                 │
   ┌────▼────┐      ┌─────▼──────┐    ┌────▼────┐
   │ Traefik │      │  Upstream  │    │ App DB  │
   │:80 :443 │◄─────┤  Services  │◄───┤  etc.   │
   └─────────┘      └────────────┘    └─────────┘
```

## Networks

### 1. Host Network (Traefik)

**Mode**: `network_mode: host`

**Why**: Enables zero-downtime deployments through container scaling:
- Multiple Traefik containers can bind to same ports simultaneously
- Scale up new version → wait for health check → scale down old version
- No port conflicts, no interruption

**Services**:
- Traefik (proxy)
- dockerproxy (Docker API access)

**Ports exposed**:
- :80 - HTTP entrypoint (web)
- :443 - HTTPS entrypoint (websecure, if configured)
- :8080 - HTTP entrypoint (web, internal)
- :8443 - HTTPS entrypoint (web-secure, internal)

**Access**:
- Direct access to host network interfaces
- Can reach containers on proxynet via container names (DNS resolution)
- Can reach local services via 127.0.0.1

### 2. proxynet Bridge Network

**Subnet**: 172.20.0.0/16
**Created by**: DNS stack (`dns/docker-compose.yml`)
**Type**: External bridge network

**Purpose**:
- Connect upstream services to Traefik
- DNS resolution between containers
- Network isolation (only accessible via Traefik)

**Connected services**:
- All upstream project services
- CrowdSec (reads Traefik logs)
- DNS honeypot (172.20.0.253)

**Special IP**:
- `172.20.0.253` - DNS honeypot (configured as DNS server for all containers)

**Configuration**:
```yaml
networks:
  proxynet:
    external: true
```

Services declare they want to join `proxynet`:
```yaml
services:
  my-app:
    networks:
      - proxynet
```

### 3. Project-Specific Networks

**Type**: User-defined bridge networks
**Scope**: Per-project isolation

**Example**:
```yaml
networks:
  default:
    name: my-project-internal
```

**Use cases**:
- App ↔ Database communication
- Service mesh within a project
- Isolation from other projects

## DNS Resolution

### Container Name Resolution

Containers on `proxynet` can reach each other by name:

```bash
# From any container on proxynet
curl http://my-app-service:3000
ping traefik-web
```

**DNS flow**:
1. Container queries DNS
2. Sent to configured DNS server (172.20.0.253 - honeypot)
3. Honeypot logs query (security monitoring)
4. Falls back to Docker's embedded DNS (127.0.0.11)
5. Docker resolves container names to IPs

### External DNS

Containers use the DNS honeypot first, then host's DNS:

```yaml
services:
  traefik:
    dns:
      - 172.20.0.253  # DNS honeypot
```

Benefits:
- Security monitoring of DNS queries
- Detect malware C2 domains
- Audit what containers are resolving

## Port Mapping

### External (Internet → Router → Host)

Router port forwards:
```
80   → Host:80    (HTTP)
443  → Host:443   (HTTPS)
8080 → Host:8080  (Traefik HTTP internal)
8443 → Host:8443  (Traefik HTTPS internal)
```

### Internal (Host Services)

```
:8888  - API server (itsup API)
:2375  - dockerproxy (secured Docker API)
:18080 - CrowdSec API (localhost only)
:7422  - CrowdSec AppSec (localhost only)
```

### Traefik Entrypoints

**Configuration** (`proxy/traefik/traefik.yml`):
```yaml
entryPoints:
  web:
    address: :8080
  web-secure:
    address: :8443
```

**Usage**:
- `web` - HTTP traffic (port 80/8080)
- `web-secure` - HTTPS traffic (port 443/8443)

Services specify which entrypoint to use via Traefik labels:
```yaml
labels:
  - traefik.http.routers.my-app.entrypoints=web-secure
```

## Traefik Routing

### Service Discovery

Traefik auto-discovers services via Docker labels:

```yaml
labels:
  - traefik.enable=true
  - traefik.http.routers.my-app.rule=Host(`example.com`)
  - traefik.http.services.my-app.loadbalancer.server.port=3000
```

**How it works**:
1. Traefik watches Docker API via dockerproxy
2. Detects containers with `traefik.enable=true`
3. Reads routing rules from labels
4. Creates routes dynamically
5. Proxies traffic to container IP:port on proxynet

### Label Generation

Labels are auto-generated from `projects/{project}/ingress.yml`:

```yaml
# projects/my-project/ingress.yml
enabled: true
ingress:
  - service: web
    domain: example.com
    port: 3000
    router: web-secure
```

Generates:
```yaml
labels:
  - traefik.enable=true
  - traefik.http.routers.my-project-web.rule=Host(`example.com`)
  - traefik.http.routers.my-project-web.entrypoints=web-secure
  - traefik.http.routers.my-project-web.tls.certresolver=letsencrypt
  - traefik.http.services.my-project-web.loadbalancer.server.port=3000
```

## Traffic Flow Examples

### HTTPS Request to Upstream Service

```
1. Client → Router:443
   ↓
2. Router → Host:443 (NAT)
   ↓
3. Traefik (host network :443)
   ├─ TLS termination
   ├─ Match router rule: Host(`example.com`)
   ├─ CrowdSec check (block if malicious)
   ↓
4. Traefik → my-app-service:3000 (proxynet)
   ↓
5. App processes request
   ↓
6. Response back through Traefik
   ↓
7. Traefik → Client (encrypted)
```

### Container → External API

```
1. Container makes outbound request
   ↓
2. Query DNS (172.20.0.253 - honeypot)
   ├─ Honeypot logs query
   ├─ Forwards to Docker DNS
   ├─ Docker forwards to host DNS
   ↓
3. Connection via proxynet bridge → host network
   ↓
4. Host routing table
   ↓
5. Router → Internet
```

**Security**: OpenSnitch monitors this and can block unauthorized connections.

### Container → Container (Same Project)

```
App container → DB container
   ↓
Both on project-specific network
   ↓
Direct IP communication (no NAT)
   ↓
Fast, low latency
```

### Container → API Server

```
1. Container → itsup.srv.instrukt.ai:443
   ↓
2. Traefik receives request (host network)
   ├─ Matches router: Host(`itsup.srv.instrukt.ai`)
   ├─ Routes to service: itsup-172-17-0-1-8888
   ↓
3. Traefik → 172.17.0.1:8888 (Docker bridge IP)
   ↓
4. API server (listening on host :8888)
```

## Network Security

### Isolation

- **proxynet**: Only services that need external access
- **Project networks**: Internal-only services (databases, caches)
- **Host network**: Only Traefik and dockerproxy

### Firewall Rules

Managed by OpenSnitch and iptables:

```bash
# Block container from accessing unauthorized external IPs
iptables -A OUTPUT -s 172.20.0.5 -d 1.2.3.4 -j DROP

# Monitor all connections
# OpenSnitch logs to SQLite database
```

### Trusted IPs

Traefik trusts specific IP ranges for forwarded headers:

```yaml
entryPoints:
  web-secure:
    forwardedHeaders:
      trustedIPs:
        - 127.0.0.0/32
        - 172.0.0.0/8
        - 10.0.0.0/8
        - 192.168.1.0/24
    proxyProtocol:
      trustedIPs:
        - 127.0.0.0/32
        - 172.0.0.0/8
        - 10.0.0.0/8
        - 192.168.1.0/24
```

Prevents IP spoofing attacks.

## Network Performance

### Why Host Network for Traefik?

**Pros**:
- No NAT overhead
- Zero-downtime scaling
- Direct kernel network stack access
- Better performance

**Cons**:
- Less isolation (acceptable for reverse proxy)
- Port conflicts if not managed carefully

### Connection Pooling

Traefik maintains connection pools to upstream services:
- Reduces connection overhead
- Reuses TCP connections
- Configurable via `serversTransport`

## Troubleshooting

### Check Network Connectivity

```bash
# List all networks
docker network ls

# Inspect proxynet
docker network inspect proxynet

# Check which containers are on proxynet
docker network inspect proxynet | jq '.[0].Containers'

# Test connectivity from container
docker exec my-container ping traefik-web
docker exec my-container curl http://other-service:3000
```

### DNS Resolution Issues

```bash
# Check container's DNS config
docker exec my-container cat /etc/resolv.conf

# Should show:
# nameserver 172.20.0.253

# Test DNS resolution
docker exec my-container nslookup google.com
docker exec my-container nslookup other-container
```

### Port Conflicts

```bash
# Check what's listening on ports
sudo netstat -tlnp | grep -E ':(80|443|8080|8443|8888)'

# Check if multiple Traefik containers
docker ps | grep traefik

# Expected during rollout: 2 containers (old + new)
# Expected normally: 1 container
```

### Traefik Can't Reach Service

```bash
# Verify service is on proxynet
docker inspect my-container | jq '.[0].NetworkSettings.Networks'

# Verify Traefik labels
docker inspect my-container | jq '.[0].Config.Labels'

# Check Traefik logs
docker logs proxy-traefik-1 | grep my-container
```

## Related Documentation

- [Architecture](architecture.md)
- [DNS Stack](stacks/dns.md)
- [Proxy Stack](stacks/proxy.md)
- [Security Monitoring](operations/monitoring.md)
