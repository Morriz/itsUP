# itsUP Secrets

SOPS-encrypted secrets for itsUP infrastructure.

## Structure

- `itsup.enc.txt` - itsUP infra secrets + API keys
- `{project}.enc.txt` - Project-specific secrets

## Usage

Secrets are automatically encrypted/decrypted by git hooks.

### Manual Operations

```bash
# Edit (decrypts, opens $EDITOR, re-encrypts on save)
sops itsup.enc.txt

# Decrypt
sops -d itsup.enc.txt > itsup.txt

# Encrypt
sops -e itsup.txt > itsup.enc.txt
```

## Setup

1. Get age private key from team lead
2. Save to `~/.config/sops/age/keys.txt`
3. Git hooks auto-decrypt on checkout/pull
