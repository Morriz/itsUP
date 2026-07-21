---
id: third-party/github-actions/workflow-secrets-and-injection
type: third-party
scope: project
description: GitHub Actions expression-injection hardening for inline run scripts, secret-redaction limits, and the Morriz/github-openvpn-connect-action optional-input semantics that make an unset VPN peer secret fail open.
---

# GitHub Actions — Workflow Secrets & Expression Injection

Curated for the `api-public-surface-scoping` work, which changes which secret the
shared reconcile workflow reads and adds a guard step around it. Sources: GitHub's
security-hardening guide and the action's own source.

## Expression injection into inline `run` scripts

- A `${{ }}` expression interpolated into a `run:` body is substituted **before**
  the shell parses the script, so the value participates in generating the shell
  program. A quote or metacharacter in the value changes what executes. GitHub
  names this the script-injection pattern and treats any context value used this
  way as untrusted.
- The recommended mitigation for an inline script is an **intermediate
  environment variable**: bind the expression in the step's `env:` map and read it
  as a shell variable, so the value reaches the shell as data rather than source.
  Double-quote the variable reference to avoid word splitting.
- The safest form overall is passing the value as an argument to an action rather
  than embedding it in a script at all.

Applied shape for a required-secret guard:

```yaml
- name: Require VPN peer secret
  env:
    OVPN_HOST: ${{ secrets.OVPN_HOST }}
  run: |
    if [ -z "$OVPN_HOST" ]; then
      echo '::error::OVPN_HOST is not set in this repository.'
      exit 1
    fi
```

The `env:` binding keeps the secret out of shell source; the quoted `"$OVPN_HOST"`
keeps an empty or whitespace value from splitting into zero arguments and
inverting the test.

## Secret redaction is not a guarantee

- Runners redact secrets only when the value is used within a job and is visible
  to the runner. GitHub states automatic redaction **is not guaranteed**.
- A transformed secret (base64, URL-encoded) is not redacted unless separately
  registered. An unredacted secret in a log means deleting the log and rotating
  the secret, not editing the log.

Consequence for guard steps: assert on emptiness only. Never echo the value, and
never include it in an error message.

## `appleboy/ssh-action` — passing secrets to a remote script

A secret written into the `script:` input is resolved by GitHub **before** the
action runs, so it becomes part of the command block the action prints and is a
command-injection input besides. The action's own boundary for this is the
`envs:` input paired with the step's `env:` map:

```yaml
- uses: appleboy/ssh-action@0ff4204d59e8e51228ff73bce53f80d53301dee2 # v1.2.5
  env:
    API_KEY: ${{ secrets.API_KEY }}
  with:
    host: ${{ secrets.SSH_HOST }}
    envs: API_KEY
    script: |
      curl -f "http://127.0.0.1:8888/reconcile" -H "Authorization: Bearer $API_KEY"
```

- **`envs:` takes variable NAMES, not `key=value` pairs.** The action's
  `action.yml` describes it as `key=value,key2=value2`; the README's documented
  usage — `envs: FOO,BAR,SHA` with the values supplied by the step's `env:` map —
  is the authoritative contract. Following the `action.yml` description would put
  the secret value back into a resolved input, defeating the purpose.
- Quote every remote reference (`"$API_KEY"`) so an empty or space-bearing value
  cannot split into extra arguments.
- Action *inputs* such as `host`, `username`, `key` and `passphrase` are outside
  this concern: they are passed as inputs, not interpolated into shell source.
- `curl -v` inside the remote script defeats the whole arrangement by tracing the
  outbound `Authorization` header into the log. Use `-f` alone.

**Pin the action when relying on this seam.** `@master` lets the
credential-transfer semantics change without review. `v1.2.5` resolves to commit
`0ff4204d59e8e51228ff73bce53f80d53301dee2`; a commit pin makes any change to the
contract an explicit, reviewable update.

## `Morriz/github-openvpn-connect-action@v3` — optional inputs fail open

Verified at commit `728a3c0657b657ab483cbcbdab7d8f5099d70601` (tag `v3`) against
both the manifest and the bundle it actually executes:

- `action.yml` declares `host` (and `port`, `protocol`, and every credential
  input) as `required: false`. Only `config_file` is required. It runs
  `dist/index.js` under `node20`.
- The executed `dist/index.js` contains `getInput("host")`, the
  `host && port && protocol` guard, and the `remote ${host} ${port} ${protocol}`
  append — the same semantics as `src/main.js`.
- An unset secret evaluates to the empty string, so the guard is skipped and the
  `remote` line is simply never written. No error is raised by the action.

**Ground behavior in `dist/`, not `src/`.** `action.yml`'s `main:` names the
committed bundle; the sources are not what runs. A repository whose bundle has
drifted from its sources would behave as the bundle says, so a source-only
reading is unverified.

**Pin this action too.** `@v3` is a movable tag; the pin above makes both the
resolved commit and its bundle contents reviewable.

The failure therefore surfaces late and obscurely inside OpenVPN's own connect
attempt rather than at the misconfigured boundary. Any repository whose committed
`.ovpn` omits its own `remote` line depends entirely on this input being set, and
must validate it explicitly at the workflow boundary.
