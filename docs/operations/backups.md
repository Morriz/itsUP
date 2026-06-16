# Backup and Disaster Recovery

Backup strategies and procedures for itsup infrastructure.

## Overview

**Backup Strategy**: Configuration-as-code with git + periodic state backups to S3.

**Philosophy**:
- **Configuration**: Version controlled in git (primary source of truth)
- **State**: The bind-mounted `upstream/` tree is tarred and backed up to S3 (see [What Gets Backed Up](#what-gets-backed-up))
- **Secrets**: Encrypted with SOPS, backed up to git
- **Logs**: Rotated locally, not archived (see [Logging](logging.md))

> **Why bind mounts, not named volumes:** `bin/backup.py` tars the on-disk `upstream/` directory. All project persistent data therefore lives under `upstream/{project}/...` as host bind mounts (e.g. `upstream/<project>/db`, `upstream/<project>/data`). Named Docker volumes would live outside `upstream/` and be invisible to this tar-based backup, so projects deliberately use bind mounts.

## What Gets Backed Up

### Git Repositories

**projects/** (Infrastructure Configuration):
```
projects/
├── itsup.yml              # Infrastructure config (with ${VAR} placeholders)
├── traefik.yml            # Traefik overrides
└── */
    ├── docker-compose.yml # Service definitions
    └── itsup-project.yml  # Routing configuration
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

`bin/backup.py` tars **only the `upstream/` directory** and uploads the single archive to S3. This includes every project's generated compose file AND its bind-mounted persistent data:
```
upstream/
└── {project}/
    ├── docker-compose.yml  # Generated compose file with Traefik labels
    └── ...                 # Bind-mounted data (db/, data/, etc.)
```

> `proxy/` (including `acme.json` and the generated `traefik.yml`) is **NOT** backed up by this script. Let's Encrypt certificates are re-issued automatically on restore.

Project directories can be excluded via the `backup.exclude` list (matched by directory name).

**Backup Method**: `bin/backup.py` script uploads to S3
- **Frequency**: Nightly via the `itsup-backup.timer` systemd timer (05:00)
- **Retention**: Newest 10 timestamped archives are kept; older ones are deleted by the script
- **Recovery**: S3 download + extract

**Configuration** (in `projects/itsup.yml`):
```yaml
backup:
  exclude: []          # project directory names to exclude
  s3:
    host: ${AWS_S3_HOST}      # S3-compatible endpoint, from secrets
    region: ${AWS_S3_REGION}  # from secrets
    bucket: ${AWS_S3_BUCKET}  # from secrets
```

**Required secrets** (`secrets/itsup.txt` or `secrets/itsup.enc.txt`): `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_S3_HOST`, `AWS_S3_REGION`, `AWS_S3_BUCKET`. The endpoint is S3-compatible (signature v4); it need not be AWS S3.

## Backup Procedures

### Manual Backup (Full)

**1. Git backup** (configuration + secrets):
```bash
cd /home/youruser/srv
git add projects/ secrets/*.enc.txt
git commit -m "Backup: $(date -Iseconds)"
git push
```

**2. S3 backup** (state):
```bash
bin/backup.py
```

**Result**: Full infrastructure backup (config + state).

### Automated Backup

The nightly S3 backup runs via the **`itsup-backup.timer` systemd timer at 05:00**, installed by `bin/install-bringup.sh` (`make install`). No cron entry is needed on a host set up that way.

If you prefer cron (or are on a host without the systemd bringup), the equivalent entry is:

```bash
0 5 * * * cd /home/youruser/srv && .venv/bin/python bin/backup.py >> /home/youruser/srv/logs/backup.log 2>&1
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
   # Backups are stored at the bucket root as itsup.tar.gz.<timestamp>
   # (no latest.tar.gz, no key prefix). Pick the newest:
   LATEST=$(aws s3 ls s3://my-backup-bucket/ | awk '/itsup.tar.gz\./{print $4}' | sort | tail -1)
   aws s3 cp "s3://my-backup-bucket/$LATEST" /tmp/itsup-backup.tar.gz
   cd /home/youruser/srv
   tar -xzf /tmp/itsup-backup.tar.gz   # extracts upstream/
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
   curl -I https://{domain}     # Test endpoints
   ```

**Total Time**: ~15-30 minutes depending on number of projects.

### Partial Restore (Single Project)

**Scenario**: Corrupted project configuration, need to restore from backup.

**Steps**:

1. **Git restore** (if in git):
   ```bash
   cd /home/youruser/srv
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

`acme.json` is **not** included in the S3 backup (only `upstream/` is). The recovery path is to let Traefik re-issue:

```bash
# Remove existing (invalid) acme.json if present
rm -f proxy/traefik/acme.json

# Restart Traefik (will request new certificates)
itsup proxy restart traefik

# Watch logs for certificate requests
itsup proxy logs traefik | grep -i certificate
```

**Note**: Let's Encrypt has rate limits (50 certs/week per registered domain). If you maintain your own out-of-band copy of `acme.json`, restore that instead to avoid re-issuance.

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
   # List timestamped archives at the bucket root
   aws s3 ls s3://my-backup-bucket/ | grep itsup.tar.gz.
   LATEST=$(aws s3 ls s3://my-backup-bucket/ | awk '/itsup.tar.gz\./{print $4}' | sort | tail -1)
   aws s3 cp "s3://my-backup-bucket/$LATEST" /tmp/itsup-backup.tar.gz

   # Verify archive integrity
   tar -tzf /tmp/itsup-backup.tar.gz | head -20
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
- The `upstream/` directory only — generated compose files **and** bind-mounted project data. Nothing else (no `proxy/`, no `acme.json`).
- Project directories named in `backup.exclude` are skipped.

**Configuration** (from `projects/itsup.yml`):
```yaml
backup:
  exclude: []          # project directory names to exclude
  s3:
    host: ${AWS_S3_HOST}      # S3-compatible endpoint (from secrets)
    region: ${AWS_S3_REGION}  # from secrets
    bucket: ${AWS_S3_BUCKET}  # from secrets
```
There is no `prefix`, `include_volumes`, or `compression` key — the archive is always gzip-compressed and the `exclude` list is the only content control.

**Output**: a single gzip tarball per run, uploaded to the bucket root with a timestamp suffix:
```
s3://my-backup-bucket/itsup.tar.gz.20260115050000
```
The script keeps the newest 10 such archives and deletes older ones. There is no `latest.tar.gz`.

**Logging**: prints progress to stdout (redirect to `logs/backup.log` in the timer/cron invocation if you want a file).

## Disaster Scenarios

### Scenario 1: Server Hardware Failure

**Impact**: Complete system loss.

**Recovery**: [Full System Restore](#full-system-restore-disaster-recovery) procedure.

**RTO** (Recovery Time Objective): 30 minutes.

**RPO** (Recovery Point Objective): Last nightly backup (up to 24 hours).

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

### Scenario 3: Corrupted Project Data

**Impact**: Lost container data (databases, uploads, etc.).

**Recovery**: Project data lives under `upstream/{project}/` as bind mounts and is included in the S3 backup. Extract the relevant subtree from the latest archive:
```bash
tar -xzf /tmp/itsup-backup.tar.gz "upstream/{project}"
itsup svc {project} restart
```

**Note**: This is exactly why projects use bind mounts under `upstream/` rather than named Docker volumes — only `upstream/` is backed up.

### Scenario 4: Certificate Expiry

**Impact**: HTTPS sites inaccessible.

**Recovery**:
```bash
# Traefik should auto-renew; if it fails, force re-issuance:
rm -f proxy/traefik/acme.json
itsup proxy restart traefik
```
`acme.json` is not in the S3 backup, so re-issuance (not restore) is the recovery path.

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

The script itself caps retention at the newest 10 archives. A lifecycle policy is optional and, if used, must match the real key shape (`itsup.tar.gz.` at the bucket root):

**Optional Lifecycle Policy**:
```json
{
  "Rules": [
    {
      "Id": "RetainDaily",
      "Status": "Enabled",
      "Prefix": "itsup.tar.gz.",
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
# If running backup.py from cron instead of the systemd timer:
MAILTO=ops@example.com
0 5 * * * cd /home/youruser/srv && .venv/bin/python bin/backup.py || echo "Backup failed!" | mail -s "BACKUP FAILURE" ops@example.com
```
When run under the `itsup-backup.timer` systemd unit, use `journalctl -u itsup-backup` / `systemctl list-timers` to monitor instead.

**S3 Monitoring**:
- Enable S3 access logging
- Set up CloudWatch alarms for backup age (alert if no new backup in 48 hours)

## Best Practices

1. **Automate backups**: nightly S3 backups via the `itsup-backup.timer` systemd timer (cron is an alternative)
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
