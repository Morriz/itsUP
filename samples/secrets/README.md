# itsUP Secrets

SOPS-encrypted secrets for itsUP infrastructure and projects.

## Overview

Secrets are encrypted with [SOPS](https://github.com/mozilla/sops) using [age](https://github.com/FiloSottile/age) encryption. Each secret file is stored as `.enc.txt` (encrypted) with plaintext `.txt` files gitignored for security.

## Structure

```
secrets/
├── .sops.yaml              # SOPS configuration (public key)
├── itsup.enc.txt           # Global secrets (all projects)
└── {project}.enc.txt       # Project-specific secrets
```

## Secret Loading

Secrets are loaded automatically when running itsUP commands:

- **Global secrets** (`itsup.enc.txt`): Loaded for all operations
- **Project secrets** (`{project}.enc.txt`): Loaded when deploying/managing specific projects

Format: `KEY=value` (one per line, no spaces around `=`)

## Quick Start

### 1. Generate Encryption Key

```bash
itsup sops-key
```

This creates:
- Private key: `~/.config/sops/age/keys.txt` (keep secret!)
- Public key: Added to `secrets/.sops.yaml` (commit to git)

### 2. Create/Edit Secrets

```bash
# Edit global secrets (auto-decrypts, opens editor, re-encrypts)
itsup edit-secret itsup

# Edit project-specific secrets
itsup edit-secret myproject
```

### 3. Commit Encrypted Secrets

```bash
# Auto-encrypts plaintext files before committing
itsup commit
```

## Manual Operations

### Encrypt/Decrypt

```bash
# Encrypt all plaintext files
itsup encrypt

# Encrypt and delete plaintext
itsup encrypt --delete

# Decrypt for bulk editing
itsup decrypt
# ... edit files ...
itsup encrypt --delete
```

### Using SOPS Directly

```bash
# Interactive edit (recommended)
sops itsup.enc.txt

# Decrypt to stdout
sops -d itsup.enc.txt

# Encrypt file
sops -e itsup.txt > itsup.enc.txt
```

## Key Rotation

Rotate encryption keys and re-encrypt all secrets:

```bash
itsup sops-key --rotate
```

This will:
1. Backup old key
2. Generate new key
3. Update `.sops.yaml`
4. Re-encrypt all secrets with new key

## Team Setup

**For new team members:**

1. Get private key from team lead (secure channel)
2. Save to `~/.config/sops/age/keys.txt` with permissions `600`:
   ```bash
   mkdir -p ~/.config/sops/age
   cat > ~/.config/sops/age/keys.txt  # paste key
   chmod 600 ~/.config/sops/age/keys.txt
   ```
3. Clone projects and secrets repos
4. Secrets auto-decrypt on checkout

**Key format:**
```
# Private key (AGE-SECRET-KEY-...)
AGE-SECRET-KEY-1XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX

# Public key (age1...)
age1qs7zacvnwffsemt96q7yh83au34dzeu7730weetdnp0ff2axjujq9n9thy
```

## Security

- ✅ **Encrypted files** (`.enc.txt`) are committed to git
- ✅ **Plaintext files** (`.txt`) are gitignored (never committed)
- ✅ **Private key** never leaves your machine
- ✅ **Public key** is safe to commit (can only encrypt, not decrypt)
- ✅ **Git hooks** auto-decrypt on checkout/pull (if key present)

## Troubleshooting

### "config file not found"

Make sure `.sops.yaml` exists in the secrets/ directory:
```bash
cat secrets/.sops.yaml
```

### "No such file or directory: age"

Install age encryption tool:
```bash
# macOS
brew install age

# Linux
sudo apt-get install age
```

### "Failed to get data key"

Your private key doesn't match the public key in `.sops.yaml`. Get the correct private key from your team lead.

### View encrypted file metadata

```bash
sops -d --extract '["sops"]' itsup.enc.txt
```

## Best Practices

1. **Never commit plaintext** - Use `itsup encrypt --delete` after editing
2. **Use itsup CLI** - Handles encryption/decryption automatically
3. **Rotate keys regularly** - Use `itsup sops-key --rotate` annually
4. **Backup private key** - Store securely (password manager, encrypted backup)
5. **One key per team** - Share same key across team members
6. **Minimal secrets** - Only store what's needed, avoid duplication
