# DNS Stack

The DNS stack provides DNS honeypot functionality for security monitoring and creates the `proxynet` network that all other services use.

## Purpose

1. **Security Monitoring**: Log all DNS queries from containers to detect malicious domains
2. **Network Foundation**: Create the `proxynet` bridge network
3. **Threat Intelligence**: Detect C2 domains, malware beacons, data exfiltration

## Architecture

```
Container → DNS Query → 172.20.0.253 (honeypot) → Log → Forward → 127.0.0.11 (Docker DNS) → 1.1.1.1 / 9.9.9.9 → Internet
```

## Components

### DNS Honeypot Container

**Image**: `4km3/dnsmasq:2.90-r3-alpine-3.22.2` (stock dnsmasq; config written inline at container start)
**IP**: 172.20.0.253 (static on proxynet)
**Port**: 53/UDP, `expose`d on proxynet only (no host port binding)

**Function**:
- Receives all DNS queries from containers
- Logs every query to stdout (`log-queries`, `log-facility=-`)
- Forwards upstream in order: `127.0.0.11` (Docker DNS, for container-name resolution) → `1.1.1.1` → `9.9.9.9` (`strict-order`, `no-resolv`)
- Transparent to applications

It boots before any Docker network exists (dnsmasq is baked into the image), because this container IS the local DNS path on boot.

## Configuration

### docker-compose.yml

Located at: `dns/docker-compose.yml`

```yaml
networks:
  proxynet:
    name: proxynet
    driver: bridge
    ipam:
      config:
        - subnet: 172.20.0.0/16
          gateway: 172.20.0.1
    driver_opts:
      encrypted: 'true'

services:
  dns-honeypot:
    image: 4km3/dnsmasq:2.90-r3-alpine-3.22.2
    container_name: dns-honeypot
    expose:
      - "53/udp"
    networks:
      proxynet:
        ipv4_address: 172.20.0.253
```

## Network: proxynet

**Subnet**: 172.20.0.0/16
**Gateway**: 172.20.0.1
**Type**: Bridge network

**Purpose**:
- Connect upstream services to Traefik
- Provide DNS honeypot to all containers
- Isolate services from direct external access

**Services using proxynet**:
- Upstream project services that have ingress (Traefik discovery)
- CrowdSec (`proxy_crowdsec`)
- DNS honeypot itself

(Traefik runs on the host network, not proxynet; it reaches upstreams via the
socket proxy and by IP/name from its own namespace.)

## Operations

### Starting DNS Stack

```bash
# Via itsup
itsup dns up

# Or directly
cd dns && docker compose up -d
```

**Dependencies**: None (DNS stack starts first)

**Created resources**:
- `proxynet` network
- DNS honeypot container

### Stopping DNS Stack

```bash
# Via itsup
itsup dns down

# Or directly
cd dns && docker compose down
```

**Warning**: Other services depend on proxynet! Stop them first:
```bash
itsup down  # Stops everything in order
```

### Viewing Logs

```bash
# Via itsup
itsup dns logs

# Or directly
docker logs dns-honeypot -f
```

### Restart

```bash
# Via itsup
itsup dns restart

# Or directly
cd dns && docker compose restart
```

## DNS Query Logging

### Log Format

```
[timestamp] DNS query from 172.20.0.5: malware-c2-domain.com A
[timestamp] DNS query from 172.20.0.18: api.legitimate.com A
```

### Threat Detection

The DNS stack itself only logs queries (no classification). Pattern analysis —
unusual TLDs, known C2 domains, DGA, beaconing frequency — is performed
downstream by the security monitor reading these logs.

### Integration with Security Monitor

The security monitor reads DNS honeypot logs and:
1. Correlates with container IPs
2. Identifies which service made the query
3. Checks against threat intelligence
4. Blocks container if malicious domain detected

## Container DNS Configuration

All containers are configured to use the DNS honeypot:

```yaml
services:
  my-app:
    dns:
      - 172.20.0.253  # DNS honeypot
      - 127.0.0.11    # Docker DNS fallback
    networks:
      - proxynet
```

Injected by `bin/write_artifacts.py` (`write_upstream`), which sets each service's
`dns: [172.20.0.253, 127.0.0.11]` unless an explicit `dns` override is declared on the ingress row.

## Security Benefits

### 1. Visibility
- Every DNS query is logged
- Know exactly what external domains containers access
- Audit trail for compliance

### 2. Threat Detection
- Detect malware C2 communication
- Identify data exfiltration attempts
- Catch compromised containers early

### 3. Network Segmentation
- Containers can't bypass DNS monitoring
- Force DNS through honeypot
- Monitor + log + forward pattern

## Troubleshooting

### DNS honeypot not responding

**Symptoms**:
- Containers can't resolve DNS
- DNS queries timeout
- Services fail to start

**Check**:
```bash
# Is container running?
docker ps | grep dns-honeypot

# Is it listening on port 53?
docker exec dns-honeypot netstat -ulnp | grep :53

# Can you reach it from host?
dig @172.20.0.253 google.com
```

**Fix**:
```bash
# Restart DNS stack
itsup dns restart

# Check logs for errors
itsup dns logs
```

### proxynet already exists error

**Symptom**:
```
Error response from daemon: network proxynet already exists
```

**Cause**: Network exists from previous run

**Fix**:
```bash
# Check what's using it
docker network inspect proxynet

# If nothing connected, remove and recreate
docker network rm proxynet
itsup dns up
```

### Containers using wrong DNS

**Symptom**: Queries not appearing in honeypot logs

**Check**:
```bash
# Check container's DNS config
docker exec my-container cat /etc/resolv.conf

# Should show:
nameserver 172.20.0.253
```

**Fix**: Regenerate container's docker-compose.yml:
```bash
itsup apply my-project
```

### DNS queries failing

**Symptom**: Queries reach honeypot but fail to resolve

**Check**:
```bash
# Test DNS resolution from container
docker exec my-container nslookup google.com

# Check honeypot is forwarding
docker logs dns-honeypot | grep -i forward
```

**Fix**: Verify honeypot has upstream DNS configured

## Performance

**Impact**: Minimal
- DNS queries are small and fast
- Honeypot adds <1ms latency
- Logging is async (doesn't block queries)

**Scalability**:
- Can handle 1000s of queries per second
- Single container sufficient for typical workload

## Related Documentation

- [Architecture](../architecture.md)
- [Networking](../networking.md)
- [Security Monitoring](../operations/monitoring.md)
- [Proxy Stack](proxy.md)
