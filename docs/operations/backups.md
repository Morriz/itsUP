# Backup and Disaster Recovery

Backup strategies and procedures for itsup infrastructure.

## Overview

**Backup Strategy**: Configuration-as-code with git + periodic state backups to S3.

**Philosophy**:
- **Configuration**: Version controlled in git (primary source of truth)
- **State**: Backed up to S3 (databases, volumes, generated artifacts)
- **Secrets**: Encrypted with SOPS, backed up to git
- **Logs**: Rotated locally, not archived (see [Logging](logging.md))

## What Gets Backed Up

### Git Repositories

**projects/** (Infrastructure Configuration):
```
projects/
├── itsup.yml              # Infrastructure config (with ${VAR} placeholders)
├── traefik.yml            # Traefik overrides
└── */
    ├── docker-compose.yml # Service definitions
    └── ingress.yml        # Routing configuration
```

**secrets/** (Encrypted Secrets):
```
secrets/
├── itsup.txt              # Shared secrets (plaintext, gitignored)
├── itsup.enc.txt          # Shared secrets (encrypted, in git)
├── {project}.txt          # Project secrets (plaintext, gitignored)
└── {project}.enc.txt      # Project secrets (encrypted, in git)
```

**Backup Method**: Git push to remote repository
- **Frequency**: On every change (manual git workflow)
- **Retention**: Unlimited (git history)
- **Recovery**: `git clone` or `git pull`

### S3 Backups (State)

**upstream/** (Generated Artifacts):
```
upstream/
└── */
    └── docker-compose.yml # Generated compose files with Traefik labels
```

**proxy/** (Proxy State):
```
proxy/
├── traefik/
│   ├── traefik.yml       # Generated Traefik config
│   ├── acme.json         # Let's Encrypt certificates
│   └── *.conf.yaml       # Dynamic configs
└── docker-compose.yml     # Proxy stack compose
```

**Container Volumes** (Optional):
```
# Project-specific persistent data
upstream/{project}/volumes/
```

**Backup Method**: `bin/backup.py` script uploads to S3
- **Frequency**: Configurable (daily recommended)
- **Retention**: S3 lifecycle policies
- **Recovery**: S3 download + restore

**Configuration** (in `projects/itsup.yml`):
```yaml
backup:
  s3:
    bucket: my-backup-bucket
    prefix: itsup/
    region: us-east-1
```

## Backup Procedures

### Manual Backup (Full)

**1. Git backup** (configuration + secrets):
```bash
cd /home/morriz/srv
git add projects/ secrets/*.enc.txt
git commit -m "Backup: $(date -Iseconds)"
git push
```

**2. S3 backup** (state):
```bash
bin/backup.py
```

**Result**: Full infrastructure backup (config + state).

### Automated Backup (Recommended)

**Cron job for daily S3 backup**:

```bash
# Edit crontab
crontab -e

# Add daily backup at 3 AM
0 3 * * * /home/morriz/srv/bin/backup.py >> /home/morriz/srv/logs/backup.log 2>&1
```

**Git backup remains manual** (commit/push when making changes).

### Pre-Deployment Backup

**Before major changes**:
```bash
# Create backup tag in git
git tag "backup-$(date +%Y%m%d-%H%M%S)"
git push --tags

# S3 backup
bin/backup.py
```

**Rationale**: Safety net before risky operations.

## Restore Procedures

### Full System Restore (Disaster Recovery)

**Scenario**: Complete system loss, rebuilding from scratch.

**Prerequisites**:
- New server with Docker installed
- Access to git repositories
- Access to S3 bucket
- SSH key for git access
- AWS credentials for S3 access

**Steps**:

1. **Clone main repository**:
   ```bash
   cd /srv
   git clone git@github.com:user/srv.git
   cd srv
   ```

2. **Install dependencies**:
   ```bash
   make install
   source env.sh
   ```

3. **Initialize configuration**:
   ```bash
   itsup init
   # Prompts for projects/ and secrets/ git URLs
   # Clones and sets up configuration
   ```

4. **Decrypt secrets**:
   ```bash
   # Decrypt all encrypted secrets
   for enc in secrets/*.enc.txt; do
       project=$(basename "$enc" .enc.txt)
       itsup decrypt "$project"
   done
   ```

5. **Restore state from S3** (optional but recommended):
   ```bash
   # Download and extract backup
   aws s3 cp s3://my-backup-bucket/itsup/latest.tar.gz /tmp/
   cd /home/morriz/srv
   tar -xzf /tmp/latest.tar.gz
   ```

6. **Deploy infrastructure**:
   ```bash
   itsup run       # Start DNS, Proxy, API, Monitor
   itsup apply     # Deploy all projects
   ```

7. **Verify**:
   ```bash
   itsup proxy logs traefik     # Check Traefik is routing
   itsup svc {project} ps       # Check each project
   curl https://{domain}/health # Test endpoints
   ```

**Total Time**: ~15-30 minutes depending on number of projects.

### Partial Restore (Single Project)

**Scenario**: Corrupted project configuration, need to restore from backup.

**Steps**:

1. **Git restore** (if in git):
   ```bash
   cd /home/morriz/srv
   git checkout HEAD -- projects/{project}/
   git checkout HEAD -- secrets/{project}.enc.txt
   itsup decrypt {project}
   ```

2. **Regenerate and deploy**:
   ```bash
   itsup apply {project}
   ```

### Certificate Restore

**Scenario**: Lost Let's Encrypt certificates (`acme.json`).

**Option 1 - Restore from S3**:
```bash
# Download latest backup
aws s3 cp s3://my-backup-bucket/itsup/latest.tar.gz /tmp/
tar -xzf /tmp/latest.tar.gz proxy/traefik/acme.json

# Restart Traefik
itsup proxy restart traefik
```

**Option 2 - Re-issue** (if backup unavailable):
```bash
# Remove existing (invalid) acme.json
rm proxy/traefik/acme.json

# Restart Traefik (will request new certificates)
itsup proxy restart traefik

# Watch logs for certificate requests
itsup proxy logs traefik | grep -i certificate
```

**Note**: Let's Encrypt has rate limits (50 certs/week per domain). Use Option 1 if possible.

### Secrets Recovery

**Scenario**: Lost decrypted secrets file.

**Steps**:

1. **Check encrypted version exists**:
   ```bash
   ls -lh secrets/{project}.enc.txt
   ```

2. **Decrypt**:
   ```bash
   itsup decrypt {project}
   ```

3. **Verify**:
   ```bash
   cat secrets/{project}.txt
   # Should show environment variables
   ```

**If encrypted file is corrupted or empty**:
- Check git history: `git log -- secrets/{project}.enc.txt`
- Restore from git: `git checkout HEAD~1 -- secrets/{project}.enc.txt`
- Last resort: Recreate from documentation or configuration management system

## Backup Verification

**Monthly backup tests recommended**:

1. **Verify git backup**:
   ```bash
   # Clone to temp directory
   git clone git@github.com:user/srv.git /tmp/test-restore
   cd /tmp/test-restore

   # Verify all files present
   ls -l projects/ secrets/
   ```

2. **Verify S3 backup**:
   ```bash
   # Download latest
   aws s3 ls s3://my-backup-bucket/itsup/
   aws s3 cp s3://my-backup-bucket/itsup/latest.tar.gz /tmp/

   # Verify archive integrity
   tar -tzf /tmp/latest.tar.gz | head -20
   ```

3. **Test decryption**:
   ```bash
   # Decrypt one secret file
   itsup decrypt itsup
   cat secrets/itsup.txt
   # Should show valid environment variables
   ```

## Backup Script Details

**Script**: `bin/backup.py`

**What it backs up**:
- `upstream/` directory (generated artifacts)
- `proxy/` directory (Traefik config + certificates)
- Optionally: container volumes

**Configuration** (from `projects/itsup.yml`):
```yaml
backup:
  s3:
    bucket: my-backup-bucket
    prefix: itsup/               # S3 key prefix
    region: us-east-1
  include_volumes: false         # Backup container volumes?
  compression: true              # Use gzip compression?
```

**Output**:
```
s3://my-backup-bucket/itsup/backup-2025-01-15-030000.tar.gz
s3://my-backup-bucket/itsup/latest.tar.gz  # Symlink to latest
```

**Logging**: Logs to `logs/backup.log` (if configured) or stdout.

## Disaster Scenarios

### Scenario 1: Server Hardware Failure

**Impact**: Complete system loss.

**Recovery**: [Full System Restore](#full-system-restore-disaster-recovery) procedure.

**RTO** (Recovery Time Objective): 30 minutes.

**RPO** (Recovery Point Objective): Last backup (24 hours if daily cron).

### Scenario 2: Accidental Configuration Deletion

**Impact**: Lost project configuration or secrets.

**Recovery**:
```bash
# Restore from git
git checkout HEAD -- projects/{project}/
git checkout HEAD -- secrets/{project}.enc.txt
itsup decrypt {project}
itsup apply {project}
```

**RTO**: 5 minutes.

**RPO**: Last git commit.

### Scenario 3: Corrupted Docker Volumes

**Impact**: Lost container data (databases, uploads, etc.).

**Recovery**:
- If S3 backup includes volumes: Extract and restore from backup
- If not: Data loss (containers must be rebuilt, data re-created)

**Prevention**: Enable `include_volumes: true` in backup config for critical projects.

### Scenario 4: Certificate Expiry

**Impact**: HTTPS sites inaccessible.

**Recovery**:
```bash
# Traefik should auto-renew, but if it fails:
rm proxy/traefik/acme.json
itsup proxy restart traefik

# Or restore from backup
aws s3 cp s3://my-backup-bucket/itsup/latest.tar.gz /tmp/
tar -xzf /tmp/latest.tar.gz proxy/traefik/acme.json
itsup proxy restart traefik
```

**RTO**: 10 minutes.

### Scenario 5: Git Repository Loss

**Impact**: Lost all configuration and secrets history.

**Recovery**:
- If git remote exists (GitHub, GitLab): Clone from remote
- If no remote: Reconstruct from S3 backup + local knowledge

**Prevention**: Always use remote git hosting (GitHub, GitLab, Gitea).

## Retention Policies

### Git Retention

**Configuration**: Unlimited history.

**Cleanup**: Manual (if needed):
```bash
# Remove old tags
git tag -d backup-20240101-000000
git push --delete origin backup-20240101-000000

# Git GC to reclaim space
git gc --prune=now
```

### S3 Retention

**Recommended Lifecycle Policy**:
```json
{
  "Rules": [
    {
      "Id": "RetainDaily",
      "Status": "Enabled",
      "Prefix": "itsup/backup-",
      "Transitions": [
        {
          "Days": 30,
          "StorageClass": "STANDARD_IA"
        },
        {
          "Days": 90,
          "StorageClass": "GLACIER"
        }
      ],
      "Expiration": {
        "Days": 365
      }
    }
  ]
}
```

**Explanation**:
- Keep all backups for 30 days (standard storage)
- Move to Infrequent Access after 30 days
- Move to Glacier after 90 days
- Delete after 1 year

**Apply**:
```bash
aws s3api put-bucket-lifecycle-configuration \
  --bucket my-backup-bucket \
  --lifecycle-configuration file://lifecycle.json
```

### Logs Retention

See [Logging Documentation](logging.md) - logs are NOT backed up, only rotated locally.

## Security Considerations

### Backup Encryption

**Git**: Secrets are encrypted with SOPS before commit.

**S3**: Enable server-side encryption:
```bash
aws s3api put-bucket-encryption \
  --bucket my-backup-bucket \
  --server-side-encryption-configuration '{
    "Rules": [{
      "ApplyServerSideEncryptionByDefault": {
        "SSEAlgorithm": "AES256"
      }
    }]
  }'
```

**Or use KMS** for better key management:
```json
{
  "SSEAlgorithm": "aws:kms",
  "KMSMasterKeyID": "arn:aws:kms:us-east-1:123456789:key/..."
}
```

### Access Control

**Git**: SSH key authentication, restrict write access.

**S3**:
- IAM user with minimal permissions (PutObject, GetObject)
- Bucket policy to restrict access
- MFA delete for production buckets

**Example IAM Policy**:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:GetObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::my-backup-bucket",
        "arn:aws:s3:::my-backup-bucket/*"
      ]
    }
  ]
}
```

### Backup Testing

**Test restores regularly** to ensure backups are valid:
- Monthly: Test decrypt secrets
- Quarterly: Test partial restore (single project)
- Yearly: Full disaster recovery drill

## Monitoring and Alerts

**Backup Success/Failure**:
- Monitor `logs/backup.log` for errors
- Set up alerts for backup failures (e.g., cron email, monitoring system)

**Example - Email on Failure**:
```bash
# In crontab
MAILTO=ops@example.com
0 3 * * * /home/morriz/srv/bin/backup.py || echo "Backup failed!" | mail -s "BACKUP FAILURE" ops@example.com
```

**S3 Monitoring**:
- Enable S3 access logging
- Set up CloudWatch alarms for backup age (alert if no new backup in 48 hours)

## Best Practices

1. **Automate backups**: Use cron for daily S3 backups
2. **Test restores**: Regular restore drills (monthly/quarterly)
3. **Version control everything**: All configuration in git
4. **Encrypt sensitive data**: SOPS for secrets, S3 encryption for backups
5. **Geographic redundancy**: Use S3 cross-region replication for critical data
6. **Document procedures**: Keep this document updated with actual practices
7. **Monitor backup health**: Alerts for failures, regular verification
8. **Separate backup access**: Different credentials for backup vs production

## Future Improvements

- **Automated restore testing**: CI/CD pipeline that tests restore procedures
- **Incremental backups**: Reduce backup time and storage for large volumes
- **Point-in-time recovery**: Database backups with transaction logs
- **Cross-region replication**: Automatic S3 replication to second region
- **Backup metrics**: Grafana dashboard for backup status and history
- **Immutable backups**: S3 Object Lock for ransomware protection
