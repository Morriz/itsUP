---
description: Caddy-served, read-only listing of files from a cloud-synced Outbox folder hosted on a Mac.
visibility: internal
---
# Outbox — Spec

## What it is

Outbox provides a simple URL that lists files from a cloud-synced folder and
lets a visitor download them. It is intended for collecting documents on the go
and retrieving them later from another computer, such as at a print shop.

The application runs on a host of type Mac. Caddy serves the folder; the itsUP
proxy owns public ingress and forwards requests to Caddy. Files are added,
renamed, organized, and removed through the cloud-storage client; the web
surface only lists and downloads them.

## Canonical fields

### Operational shape

- The source is a cloud-synced folder named `Outbox` on the Mac host.
- Caddy exposes the folder as a browser directory listing.
- A per-user macOS LaunchAgent supervises Caddy in the user's GUI session so it
  retains access to that user's cloud-storage folder.
- The itsUP proxy maps the configured public URL to Caddy.
- The cloud folder stays locally materialized; on-demand cloud placeholders are
  not a reliable serving surface.
- macOS privacy controls and the host firewall form the boundary between Caddy,
  the cloud folder, and the itsUP proxy.
- Directory listing and file download are supported.
- Uploading and file management through the browser are not supported.

### Configuration ownership

- The Mac runtime repository owns `Caddyfile`,
  `ai.instrukt.outbox.plist`, and the runtime `README.md`.
- The itsUP repository owns ingress in `projects/outbox/itsup-project.yml`.
- Concrete machine identity, network addresses, listener ports, public domains,
  and cloud-folder paths stay in those runtime-state sources rather than this
  global contract.

### Logs

Caddy writes lifecycle and error events as structured JSON to
`~/.local/state/instrukt-ai/outbox/outbox.log`; HTTP access logging remains
disabled. Caddy-side rolling is disabled so the host's shared newsyslog service
is the single rotation owner.

- Follow current events:
  `tail -F ~/.local/state/instrukt-ai/outbox/outbox.log`
- Show warnings and errors:
  `jq -Rrc 'fromjson? | select(.level == "warn" or .level == "error")' ~/.local/state/instrukt-ai/outbox/outbox.log`
- Find retained rolls:
  `ls -lt ~/.local/state/instrukt-ai/outbox/outbox.log*`

The exact Outbox rule in `~/.config/instrukt-ai/newsyslog.conf` takes
precedence over the generic service-log glob. On rotation it sends `SIGTERM`
through Caddy's PID file; the per-user LaunchAgent's `KeepAlive` restarts Caddy,
which opens the fresh log inode. The shared rule keeps five compressed rolls.

### Operational boundaries

| Symptom | Owning boundary |
| --- | --- |
| A cloud file is missing or unavailable | Cloud synchronization or local materialization on the Mac host |
| Caddy is running but cannot list the folder | macOS privacy access for the user's cloud-storage folder |
| Caddy is unreachable from the proxy | Host networking, firewall, or the Caddy process |
| Caddy works directly but the URL fails | itsUP reverse-proxy routing or public ingress |
| The service does not return after a restart | The per-user LaunchAgent and GUI session |

## Known caveats

- The service is intentionally limited to listing and downloading files.
- Access control, when required, is owned by the ingress layer rather than this
  application.
- Runtime and access logging are distinct: the house-managed runtime log is
  retained; per-request access logging is not enabled.
