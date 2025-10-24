# The Key Architectural Insight

## The Problem

**Original approach:** External `db.yml` with all configuration + secrets mixed together.

This created:
- Secret management complexity
- Configuration not in version control
- Magic file that must exist
- Hard to share setup
- Two sources of truth (db.yml + templates)

## The Insight

**Maurice's realization:**

> "We should make certain things configurable like rate limiting etc. All needs to be consolidated except the secret key. I want all .sample files in `samples/` folder and put in the right location upon `itsup init` command."

**Translation:**

**Everything should be in git except the SOPS encryption key.**

Not "some things in git, some in db.yml" - **EVERYTHING**:
- Infrastructure config → `projects/traefik.yml` (committed)
- Project definitions → `projects/*/docker-compose.yml` (committed)
- Templates → `tpl/` (committed)
- Samples → `samples/` (committed)

**Only secrets are external** → encrypted in `secrets/` submodule.

## The Transformation

### Before (Complex)

```
db.yml (not in git, magic file)
  ├── Infrastructure config
  ├── Plugin config
  ├── Secrets (plaintext!)
  └── Project definitions

.env (not in git)
  ├── Runtime config
  ├── Infrastructure config
  └── More secrets

tpl/ (in git)
  └── Templates

User must:
1. Create db.yml manually
2. Fill in secrets
3. Remember what goes where
4. No version control
```

### After (Simple)

```
samples/ (in git, committed)
  ├── traefik.yml.j2 (template)
  └── secrets/global.txt.sample

projects/ (PUBLIC submodule, committed)
  ├── traefik.yml (infrastructure, from sample)
  └── my-app/
      ├── docker-compose.yml
      └── traefik.yml

secrets/ (PRIVATE submodule, encrypted)
  ├── global.enc.txt
  └── my-app.enc.txt

User does:
1. itsup init (copies samples → projects, prompts for values)
2. Fill in secrets/global.txt
3. Encrypt with SOPS
4. Commit projects/ to git
5. Done!
```

## Why This Matters

### Shareability

**Before:**
- Can't share setup (secrets mixed in db.yml)
- Others must recreate db.yml manually
- No template to follow

**After:**
- projects/ submodule is PUBLIC - share on GitHub!
- samples/ provides templates
- Community can contribute stacks
- secrets/ stays private, encrypted

### Version Control

**Before:**
- db.yml not in git (has secrets)
- No history of infrastructure changes
- No collaboration possible

**After:**
- Everything in git (except secrets)
- Full history of changes
- Team collaboration via git
- Can review changes before deploying

### Initialization

**Before:**
- Copy db.yml.sample → db.yml
- Fill in 752 lines manually
- Easy to miss things
- No validation

**After:**
- `itsup init` prompts for values
- Renders template with defaults
- Validates input
- Creates correct structure

### Simplicity

**Before:**
- db.yml (custom format)
- .env (environment vars)
- Templates (Jinja2)
- Secrets (mixed in)

**After:**
- projects/traefik.yml (config, committed)
- secrets/ (encrypted, gitignored)
- samples/ (templates)
- That's it!

## The Pattern

This follows a common pattern in modern infrastructure:

**Separate config from secrets, commit config:**

- Kubernetes: Manifests in git, secrets in Vault/Sealed Secrets
- Terraform: .tf files in git, variables in encrypted .tfvars
- Ansible: Playbooks in git, secrets in Ansible Vault
- Docker Swarm: Configs in git, secrets via docker secret

**itsUP now:**
- Config in git (`projects/traefik.yml`)
- Secrets encrypted (`secrets/*.enc.txt` via SOPS)
- Templates for initialization (`samples/`)

## Implementation Principles

1. **Declarative over imperative**
   - Describe what you want (projects/traefik.yml)
   - Not how to get there (no complex scripts)

2. **Explicit over implicit**
   - All config visible in git
   - No magic defaults hidden in code

3. **Shareable by default**
   - projects/ submodule is public
   - Anyone can use your stacks
   - secrets/ stays private

4. **Simple initialization**
   - `itsup init` sets up everything
   - Prompts for values
   - Creates correct structure

5. **One source of truth**
   - Not db.yml + templates
   - Just: projects/ + secrets/

## Next Steps

Update IMPLEMENTATION.md to reflect this architecture:

1. Create samples/ directory structure
2. Build `itsup init` command
3. Migrate current db.yml → projects/traefik.yml
4. Test full workflow
5. Document for users

---

**Bottom line:** Everything in git except SOPS key. Simple, shareable, version-controlled.
