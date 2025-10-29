# Troubleshooting Guide

Common issues and solutions for itsup infrastructure.

## General Troubleshooting Steps

### 1. Check Status

```bash
itsup status              # Infrastructure status
docker ps -a              # All containers
docker network ls         # Networks
```

### 2. Check Logs

```bash
itsup proxy logs traefik  # Traefik logs
itsup svc {project} logs  # Project logs
tail -f logs/*.log        # System logs (access, api, monitor)
```

### 3. Validate Configuration

```bash
itsup validate            # All projects
itsup validate {project}  # Specific project
```

### 4. Restart Services

```bash
itsup svc {project} restart     # Restart project
itsup proxy restart traefik     # Restart Traefik
itsup run                       # Restart everything
```

## Infrastructure Issues

### DNS Stack Won't Start

**Symptom**: `itsup dns up` fails with network error.

**Possible Causes**:
1. Port 53 already in use
2. Network conflict
3. Docker daemon not running

**Solutions**:

**Check port 53**:
```bash
sudo netstat -tlnp | grep :53
# Or
sudo lsof -i :53
```

**If systemd-resolved using port 53**:
```bash
# Disable stub resolver
sudo sed -i 's/#DNSStubListener=yes/DNSStubListener=no/' /etc/systemd/resolved.conf
sudo systemctl restart systemd-resolved
```

**Check Docker daemon**:
```bash
sudo systemctl status docker
sudo systemctl start docker  # If not running
```

**Check for conflicting networks**:
```bash
docker network ls | grep proxynet
docker network rm proxynet  # If exists but corrupted
itsup dns up  # Will recreate
```

### Proxy Stack Won't Start

**Symptom**: `itsup proxy up` fails or Traefik not responding.

**Check Traefik logs**:
```bash
itsup proxy logs traefik
```

**Common errors and fixes**:

**"Error while creating certificate"**:
```bash
# Let's Encrypt rate limit hit
# Wait 1 hour or use staging environment
vim projects/traefik.yml
# Add:
certificatesResolvers:
  letsencrypt:
    acme:
      caServer: https://acme-staging-v02.api.letsencrypt.org/directory
```

**"Cannot connect to Docker daemon"**:
```bash
# dockerproxy not running or misconfigured
itsup proxy logs dockerproxy

# Check dockerproxy is accessible
curl http://localhost:2375/version  # Should return JSON

# Restart dockerproxy
itsup proxy restart dockerproxy
```

**"Address already in use :80"**:
```bash
# Another service using port 80
sudo netstat -tlnp | grep :80

# Stop conflicting service
sudo systemctl stop nginx  # Or apache2, etc.
```

### API Won't Start

**Symptom**: `bin/start-api.sh` fails or API not responding.

**Check API logs**:
```bash
tail -f logs/api.log
```

**Common issues**:

**"ModuleNotFoundError"**:
```bash
# Missing dependencies
source .venv/bin/activate
pip install -r requirements.txt
```

**"Port 8080 already in use"**:
```bash
# Find process using port
sudo lsof -i :8080
# Kill or change API port
```

**"Permission denied"**:
```bash
# Check file permissions
ls -l bin/start-api.sh
chmod +x bin/start-api.sh
```

### Monitor Won't Start

**Symptom**: `itsup monitor start` fails.

**Common causes**:

**"Permission denied (eBPF)"**:
```bash
# Monitor requires root for eBPF
sudo itsup monitor start
```

**"OpenSnitch database not found"**:
```bash
# Check OpenSnitch is installed
sudo systemctl status opensnitch

# Check database exists
ls -l /var/lib/opensnitch/opensnitch.sqlite3

# Start without OpenSnitch integration
itsup monitor start  # Without --use-opensnitch flag
```

## Project Deployment Issues

### Deployment Fails

**Symptom**: `itsup apply {project}` fails with error.

**Check deployment logs**:
```bash
itsup apply {project} --verbose
```

**Common errors**:

**"Service '{service}' failed to build"**:
```bash
# Build context issue or Dockerfile error
# Check Dockerfile syntax
docker build projects/{project}/

# Check build context
ls projects/{project}/
```

**"Cannot start service: port already allocated"**:
```bash
# Port conflict with another container
docker ps | grep {port}

# Change port in docker-compose.yml or stop conflicting container
```

**"Network 'proxynet' not found"**:
```bash
# DNS stack not running
itsup dns up

# Verify network exists
docker network ls | grep proxynet
```

**"Error while fetching server API version"**:
```bash
# Docker daemon not running or not accessible
sudo systemctl status docker
sudo systemctl start docker
```

### Container Keeps Restarting

**Symptom**: Container starts but immediately exits and restarts.

**Check container logs**:
```bash
itsup svc {project} logs {service}
```

**Common causes**:

**Application crash on startup**:
- Check logs for error messages
- Verify environment variables are set correctly
- Test image manually: `docker run -it {image} sh`

**Health check failing**:
```bash
# Check health check status
docker inspect {container} | jq '.[0].State.Health'

# Disable health check temporarily (for debugging)
vim projects/{project}/docker-compose.yml
# Comment out healthcheck section
itsup apply {project}
```

**Missing volume or file**:
```bash
# Check volume mounts
docker inspect {container} | jq '.[0].Mounts'

# Verify host paths exist
ls -l /path/to/volume
```

### Service Not Reachable

**Symptom**: Container running but domain returns 404 or connection refused.

**Check step-by-step**:

**1. Verify container is running**:
```bash
itsup svc {project} ps
docker ps | grep {project}
```

**2. Check container network**:
```bash
docker inspect {container} | jq '.[0].NetworkSettings.Networks'
# Should show connection to proxynet
```

**3. Check Traefik sees the service**:
```bash
itsup proxy logs traefik | grep {project}
# Should show "Adding route" or "Server added"
```

**4. Check Traefik labels**:
```bash
docker inspect {container} | jq '.[0].Config.Labels' | grep traefik
# Should show traefik.enable=true and routing labels
```

**5. Test direct access** (bypass Traefik):
```bash
# Find container IP
docker inspect {container} | jq -r '.[0].NetworkSettings.Networks.proxynet.IPAddress'

# Test directly
curl http://{container-ip}:{port}
```

**6. Test via Traefik**:
```bash
# Test with Host header
curl -H "Host: {domain}" http://localhost/

# Should return service response
```

**Common fixes**:

**Missing Traefik labels**:
```bash
# Regenerate config
itsup apply {project}

# Verify labels in generated file
grep "traefik.enable" upstream/{project}/docker-compose.yml
```

**Wrong domain in ingress.yml**:
```bash
vim projects/{project}/ingress.yml
# Verify domain matches DNS/host file
itsup apply {project}
```

**Service not listening on configured port**:
```bash
# Check what port service actually uses
docker exec {container} netstat -tlnp

# Update ingress.yml to match actual port
```

## Network Issues

### Cannot Reach External Services

**Symptom**: Container can't reach internet or external APIs.

**Check container connectivity**:
```bash
# Test DNS resolution
docker exec {container} nslookup google.com

# Test internet connectivity
docker exec {container} ping -c 3 8.8.8.8

# Test HTTPS
docker exec {container} curl https://www.google.com
```

**Common causes**:

**DNS not working**:
```bash
# Check container's DNS config
docker inspect {container} | jq '.[0].HostConfig.Dns'

# Use Docker's default DNS
vim projects/{project}/docker-compose.yml
# Remove any custom DNS settings
```

**Firewall blocking**:
```bash
# Check iptables rules
sudo iptables -L DOCKER-USER -n -v

# Check if monitor blocked the connection
itsup monitor logs | grep {container}

# Whitelist destination
echo "destination-ip-or-domain" >> config/monitor-whitelist.txt
itsup monitor restart
```

**Network isolation**:
```bash
# Verify container has internet access
docker run --rm --network {network} alpine ping -c 3 8.8.8.8

# If fails, check Docker network configuration
docker network inspect {network}
```

### Inter-Container Communication Fails

**Symptom**: Container A can't reach container B.

**Check both containers are on same network**:
```bash
docker network inspect proxynet
# Should show both containers
```

**Test connectivity**:
```bash
# From container A
docker exec {container-a} ping {container-b}
docker exec {container-a} curl http://{container-b}:{port}
```

**Common fixes**:

**Not on same network**:
```yaml
# In docker-compose.yml
services:
  app:
    networks:
      - proxynet
      - backend
  db:
    networks:
      - backend  # Add proxynet if needed
```

**Wrong hostname**:
```bash
# Use service name as hostname (not container name)
# Correct: http://db:5432
# Wrong: http://project-db-1:5432
```

## TLS/HTTPS Issues

### Certificate Not Issued

**Symptom**: HTTPS returns "certificate not valid" or "NET::ERR_CERT_AUTHORITY_INVALID".

**Check certificate status**:
```bash
itsup proxy logs traefik | grep -i certificate
```

**Common causes**:

**Rate limit hit**:
```
Error while obtaining certificate: too many certificates already issued
```
**Fix**: Wait 1 hour or use staging server (see Proxy Stack Won't Start).

**Challenge failed**:
```
Error while obtaining certificate: challenge failed
```
**Fix**:
```bash
# Verify domain DNS points to server
nslookup {domain}

# Verify port 80 is accessible from internet
curl http://{domain}

# Check Traefik logs for specific challenge error
itsup proxy logs traefik | grep -i challenge
```

**Fix by forcing renewal**:
```bash
# Remove certificate (forces re-issue)
rm proxy/traefik/acme.json
itsup proxy restart traefik

# Watch certificate issuance
itsup proxy logs traefik | grep -i certificate
```

### Certificate Expired

**Symptom**: HTTPS works but browser shows "certificate expired".

**Check certificate expiry**:
```bash
echo | openssl s_client -connect {domain}:443 2>/dev/null | openssl x509 -noout -dates
```

**Auto-renewal should handle this**. If not:

**Force renewal**:
```bash
rm proxy/traefik/acme.json
itsup proxy restart traefik
```

**Check renewal is working**:
```bash
# Traefik should log renewal attempts
itsup proxy logs traefik | grep -i renew
```

### Mixed Content Warnings

**Symptom**: HTTPS site loads but browser shows "mixed content" warnings.

**Cause**: Site serving HTTP resources on HTTPS page.

**Fix in application**:
- Use protocol-relative URLs: `//cdn.example.com/script.js`
- Or force HTTPS: `https://cdn.example.com/script.js`
- Add middleware to Traefik to enforce HTTPS headers

**Add security headers**:
```yaml
# In projects/traefik.yml
http:
  middlewares:
    security-headers:
      headers:
        forceSTSHeader: true
        stsSeconds: 31536000
        stsIncludeSubdomains: true
        contentSecurityPolicy: "upgrade-insecure-requests"
```

```yaml
# In ingress.yml
ingress:
  - service: web
    middleware: [security-headers]
```

## Secret Issues

### Secrets Not Loading

**Symptom**: Container starts but environment variables are empty or undefined.

**Check secrets file exists**:
```bash
ls -l secrets/{project}.txt
cat secrets/{project}.txt | grep {VAR}
```

**Decrypt if encrypted**:
```bash
itsup decrypt {project}
```

**Verify variable in compose file**:
```bash
grep {VAR} projects/{project}/docker-compose.yml
# Should show: - VAR=${VAR}
```

**Check container environment**:
```bash
docker exec {container} env | grep {VAR}
```

**Force reload**:
```bash
rm projects/{project}/.config_hash
itsup apply {project}
```

### Encryption/Decryption Fails

**Symptom**: `itsup encrypt` or `itsup decrypt` fails.

**Check SOPS is installed**:
```bash
sops --version
```

**Check SOPS configuration**:
```bash
cat .sops.yaml
```

**Check GPG/age keys**:
```bash
# For GPG
gpg --list-secret-keys

# For age
ls -l ~/.config/sops/age/keys.txt
```

**Manual decryption** (debug):
```bash
sops -d secrets/{project}.enc.txt
```

**If corrupt, restore from git**:
```bash
git checkout HEAD -- secrets/{project}.enc.txt
itsup decrypt {project}
```

## Performance Issues

### High CPU Usage

**Symptom**: Server CPU constantly high.

**Check which container**:
```bash
docker stats --no-stream
# Shows CPU usage per container
```

**Inspect container**:
```bash
# Check process list
docker exec {container} ps aux

# Check logs for errors
itsup svc {project} logs {service}
```

**Common causes**:

**Restart loop**: Container crashing and restarting constantly
- Fix: Check logs, fix application error

**Infinite loop**: Application bug causing CPU spin
- Fix: Stop container, fix bug, redeploy

**Resource exhaustion**: Container needs more CPU
- Fix: Add resource limits or increase host capacity

### High Memory Usage

**Symptom**: Server memory constantly high or OOM errors.

**Check which container**:
```bash
docker stats --no-stream
# Shows memory usage per container
```

**Add memory limits** (prevent one container from hogging all memory):
```yaml
# In docker-compose.yml
services:
  app:
    deploy:
      resources:
        limits:
          memory: 512M
        reservations:
          memory: 256M
```

**Check for memory leaks**:
```bash
# Monitor over time
watch -n 5 "docker stats --no-stream | grep {container}"
```

### Slow Response Times

**Symptom**: Application responds slowly or times out.

**Check Traefik logs**:
```bash
tail -f logs/access.log
# Look for response times (last column in CLF format)
```

**Test direct vs through Traefik**:
```bash
# Direct (should be fast)
time curl http://{container-ip}:{port}

# Through Traefik (compare)
time curl https://{domain}
```

**If Traefik is slow**:
- Check middleware (auth, rate limiting can slow requests)
- Check Traefik logs for errors
- Check Traefik resource usage

**If application is slow**:
- Check application logs
- Check database connection
- Profile application

## Docker Issues

### Docker Daemon Not Responding

**Symptom**: Any docker command hangs or fails.

**Check daemon status**:
```bash
sudo systemctl status docker
```

**Restart daemon**:
```bash
sudo systemctl restart docker
```

**Check logs**:
```bash
sudo journalctl -u docker -n 100
```

### Disk Space Issues

**Symptom**: "no space left on device" errors.

**Check disk usage**:
```bash
df -h
docker system df  # Docker-specific disk usage
```

**Clean up Docker**:
```bash
# Remove stopped containers
docker container prune -f

# Remove unused images
docker image prune -a -f

# Remove unused volumes
docker volume prune -f

# Remove unused networks
docker network prune -f

# All-in-one cleanup
docker system prune -a --volumes -f
```

**For itsup containers specifically**:
```bash
itsup down --clean  # Removes stopped itsup containers
```

### Cannot Remove Container

**Symptom**: `docker rm` fails with "container is running" or "device or resource busy".

**Force stop and remove**:
```bash
docker stop -t 1 {container}  # Stop with 1s timeout
docker rm -f {container}      # Force remove
```

**If still fails**:
```bash
# Check if container is being recreated
docker events | grep {container}

# Restart Docker daemon
sudo systemctl restart docker
```

## Getting Help

### Collecting Debug Information

**Before asking for help, collect**:

1. **System information**:
```bash
uname -a
docker --version
docker compose version
```

2. **itsup version**:
```bash
itsup --version
git log -1
```

3. **Status**:
```bash
itsup status
docker ps -a
docker network ls
```

4. **Logs** (with verbose output):
```bash
itsup apply {project} --verbose > debug.log 2>&1
```

5. **Configuration** (redact secrets):
```bash
cat projects/{project}/docker-compose.yml
cat projects/{project}/ingress.yml
```

### Where to Get Help

- **GitHub Issues**: https://github.com/user/srv/issues
- **Project README**: Check for troubleshooting section
- **Docker Docs**: https://docs.docker.com/
- **Traefik Docs**: https://doc.traefik.io/traefik/

### Common Pitfalls

1. **Editing `upstream/` instead of `projects/`**
   - Always edit source (`projects/`), not generated artifacts

2. **Forgetting to decrypt secrets**
   - Run `itsup decrypt {project}` after cloning repo

3. **Not loading secrets at deployment**
   - `itsup apply` loads secrets automatically
   - Manual `docker compose` commands need `env` parameter

4. **Committing plaintext secrets**
   - Only commit `.enc.txt` files
   - `.txt` files are gitignored

5. **Not restarting after config changes**
   - `itsup apply` regenerates and restarts
   - Manual changes to `upstream/` are lost on next apply
