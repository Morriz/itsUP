# Container Security Monitor - Roadmap & Issues

> **📋 See [ANALYSIS.md](ANALYSIS.md) for comprehensive technical analysis**

## TL;DR - Key Findings

**System Status:** ⚠️ Working but overcomplicated + ✅ Secrets properly gitignored (not as critical as initially thought)

**Main Issues:**
1. **Abstraction Overload** - 5 layers between user command and docker (bash → Python → Jinja2 → compose → docker)
2. **Secret Duplication** - Same credentials repeated 6+ times in db.yml (SMTP, OpenAI keys)
3. **Script Sprawl** - 25 files doing what could be 10 files
4. **Claude Tax** - ~20 tool calls per session just to understand the system
5. **Monolithic db.yml** - 752 lines, growing out of proportion

**✅ DECIDED: Architecture V2** - Everything in git except SOPS key

**Key Changes:**
- ❌ **db.yml eliminated** - split into `projects/traefik.yml` (infrastructure) + `secrets/` (encrypted)
- ✅ **samples/** directory with templates for initialization
- ✅ **`itsup init`** command to setup new installation
- ✅ All configuration committed to git (no magic external files)
- ✅ Only SOPS encryption key stays external

**Read These:**
1. [KEY-INSIGHT.md](KEY-INSIGHT.md) - **START HERE** - Why V2 is better
2. [ARCHITECTURE-V2.md](ARCHITECTURE-V2.md) - Complete V2 design
3. [IMPLEMENTATION.md](IMPLEMENTATION.md) - Step-by-step execution plan (✅ UPDATED for V2)
4. [ANALYSIS.md](ANALYSIS.md) - Original analysis

---

## Current Architectural Issues

### 1. CLI Architecture (bash + python hybrid)

**Problem:**
- Architecturally unsound mix of bash functions and python scripts
- Steep learning curve: bash → Python → Jinja2 → docker compose → docker rollout
- Forces context learning on every Claude interaction (~20 tool calls, expensive, error-prone)
- Error messages buried in 5 layers of abstraction

**What Works:**
- Single source of truth (db.yml)
- Smart change detection (only rollout when config changed)
- Zero-downtime updates (docker rollout integration)
- Work from project root (no cd into subdirectories)
- Direct service targeting (`dcu project service`)

**Analysis:**
- 25 scripts totaling ~1311 LOC
- 9 tiny wrappers (3-7 lines each) that could be consolidated
- Inconsistent patterns (some Python, some bash, some mixed)
- Could reduce to ~10 files (~60% consolidation)

**See:** [ANALYSIS.md Section 1](ANALYSIS.md#1-cli-architecture-deep-dive) for details

### 2. 🔥 Secrets Management CRISIS

**CRITICAL SECURITY ISSUE:**
- **~50+ secrets in PLAINTEXT in db.yml committed to git**
- API keys: OpenAI, Anthropic, CrowdSec, service keys
- OAuth secrets: GitHub, Google, Slack
- Database passwords: 15+ services
- SMTP credentials: duplicated 6+ times (same Brevo creds)
- All readable by anyone with repo access
- Git history contains all historical secrets

**Immediate Actions Required:**
- [ ] Add db.yml to .gitignore TODAY
- [ ] Create db.yml.template with placeholders
- [ ] Move secrets to encrypted file (SOPS/git-crypt)
- [ ] Add pre-commit hook to prevent secret commits
- [ ] Rotate all exposed credentials
- [ ] Consolidate duplicate secrets

**See:** [ANALYSIS.md Section 2](ANALYSIS.md#2-secrets-management-crisis) for full inventory

### 3. bin/* Scripts Sprawl

**Current State:**
- 25 files, ~1311 LOC
- 9 tiny wrappers (3-7 lines): install, start-*, test, lint, format, tail-logs
- 6 small utilities (12-31 lines): validate, apply, export-env
- 4 medium scripts (79-262 lines): backup, format-logs, docker_monitor
- 1 large script (433 lines): analyze_threats

**Issues:**
- No consistent pattern (some Python, some bash)
- Redundant wrappers (9 tiny scripts that just call other scripts)
- Hard to discover what exists
- Unclear which script does what

**Consolidation Plan:**
- [ ] Create single `itsup` CLI (Python Click/Typer)
- [ ] Migrate bin/* to subcommands
- [ ] Remove lib/functions.sh
- [ ] Keep Makefile for convenience
- [ ] Result: 25 files → ~10 files

**See:** [ANALYSIS.md Section 1](ANALYSIS.md#1-cli-architecture-deep-dive) and [Appendix](ANALYSIS.md#appendix-file-inventory)

### 4. db.yml as Single Source of Truth

**What Works:**
- Declarative desired state
- Pydantic validation ensures correctness
- Centralized infrastructure definition
- Project-level env vars and dependencies

**What Doesn't Work:**
- Secrets inclusion (see issue #2)
- No dev/staging/prod differentiation
- Limited docker compose feature coverage
- `additional_properties` escape hatch shows abstraction leakage

**Potential Improvements:**
- Split into multiple files (projects/*.yml)
- Use encrypted secrets.enc.yml
- Add environment overlays (base/prod/dev)
- Or embrace docker compose directly

**See:** [ANALYSIS.md Section 3](ANALYSIS.md#3-dbyml-as-single-source-of-truth)

---

## Architectural Options

### Option A: Simplify CLI (Recommended ⭐)

**Keep:** db.yml concept, smart updates, zero-downtime rollout
**Change:** Consolidate to single `itsup` CLI, remove bash layer, fix secrets

```bash
itsup apply [project] [service]      # Smart deploy
itsup validate                        # Validate db.yml
itsup backup                          # S3 backup
itsup monitor start/stop/report       # Security monitor
itsup logs [service]                  # Tail logs
```

**Benefits:**
- Single entry point (easier for Claude)
- Standard primitives (docker compose, make)
- Keeps UX benefits (work from root, smart updates)
- Fewer layers (4 instead of 5)

### Option B: Embrace Docker Compose Fully

**Remove:** db.yml abstraction, template generation
**Use:** Pure docker compose + helper scripts

**Benefits:**
- Claude knows docker compose natively
- Standard tooling
- No custom DSL

**Drawbacks:**
- Lose single source of truth
- Lose smart change detection
- Lose automatic Traefik router generation

### Option C: Hybrid Approach

**Keep:** db.yml for high-level metadata only
**Use:** docker-compose.yml for service definitions

```yaml
# Simplified db.yml
projects:
  - name: my-app
    compose_file: upstream/my-app/docker-compose.yml
    domains: [app.example.com]
    backup: true
```

**See:** [ANALYSIS.md Section 4](ANALYSIS.md#4-architectural-alternatives) for full comparison

---

## Recommended Roadmap

### 🔥 URGENT - Security (Do Immediately)
- [ ] Add db.yml to .gitignore
- [ ] Create db.yml.template
- [ ] Move secrets to .env.secrets (SOPS encrypted)
- [ ] Add pre-commit hook to block secret commits
- [ ] Document secret rotation process
- [ ] **Priority: CRITICAL - Do before anything else**

### Phase 1: Stabilize (Week 1)
- [x] Complete technical analysis (ANALYSIS.md)
- [ ] Secure secrets (see URGENT above)
- [ ] Add integration tests for current system
- [ ] Document architecture flow
- [ ] Create troubleshooting guide

### Phase 2: Simplify CLI (Weeks 2-3)
- [ ] Build new `itsup` CLI (Python Click/Typer)
- [ ] Migrate bin/* to subcommands:
  - `itsup apply` (from apply.py)
  - `itsup validate` (from validate-db.py)
  - `itsup backup` (from backup.py)
  - `itsup monitor {start,stop,report}` (from monitor scripts)
  - `itsup logs` (from tail-logs.sh)
- [ ] Remove lib/functions.sh (bash layer)
- [ ] Update CLAUDE.md with simpler instructions
- [ ] Test migration doesn't break deployments

### Phase 3: Secrets Management (Weeks 3-4)
- [ ] Implement SOPS encryption for db.yml
- [ ] Consolidate duplicate secrets (SMTP, OpenAI keys)
- [ ] Add env var interpolation: `${SMTP_PASSWORD}`
- [ ] Migrate all projects to new secret format
- [ ] Rotate all exposed credentials
- [ ] Document secret access patterns

### Phase 4: Architecture Refinement (Weeks 5-6)
- [ ] Decide on Option A/B/C (default: A)
- [ ] Prototype chosen approach
- [ ] Migrate one project as proof of concept
- [ ] Add environment support (dev/staging/prod)
- [ ] Comprehensive testing

### Phase 5: Polish (Week 7+)
- [ ] Performance optimization
- [ ] User documentation
- [ ] Migration guide
- [ ] Cleanup old scripts
- [ ] Announce new architecture

---

## Discussion Topics

**Questions for Maurice:**
1. **Security urgency?** - Should we pause all other work to fix secrets immediately?
2. **Architecture preference?** - Option A (simplify), B (pure compose), or C (hybrid)?
3. **Migration risk tolerance?** - Big bang or incremental per-project migration?
4. **What's most painful right now?** - What should we prioritize after security?
5. **Secret rotation feasibility?** - Can we rotate all exposed credentials? Any blockers?

---

## Success Metrics

**How we'll know this worked:**

1. **Claude Efficiency:** Onboarding drops from ~20 tool calls to <5
2. **Security:** Zero secrets in plaintext, audit trail exists
3. **Developer Experience:** Clear mental model, errors are actionable
4. **Maintainability:** New features require <3 file edits

**See:** [ANALYSIS.md Section 7](ANALYSIS.md#7-success-metrics) for full metrics
