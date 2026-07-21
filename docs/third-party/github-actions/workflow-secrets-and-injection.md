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

## `Morriz/github-openvpn-connect-action@v3` — optional inputs fail open

Verified against the action's source, not its README:

- `action.yml` declares `host` (and `port`, `protocol`, and every credential
  input) as `required: false`. Only `config_file` is required.
- `src/main.js` gates the peer line on all three being truthy:
  `if (host && port && protocol)` — when satisfied it appends
  `remote ${host} ${port} ${protocol}` to the client config.
- An unset secret evaluates to the empty string, so the guard is skipped and the
  `remote` line is simply never written. No error is raised by the action.

The failure therefore surfaces late and obscurely inside OpenVPN's own connect
attempt rather than at the misconfigured boundary. Any repository whose committed
`.ovpn` omits its own `remote` line depends entirely on this input being set, and
must validate it explicitly at the workflow boundary.
