---
description: Browser-based, read-only listing of files from a cloud-synced Outbox folder hosted on a Mac.
visibility: internal
---
# Outbox — Spec

## What it is

Outbox provides a simple URL that lists files from a cloud-synced folder and
lets a visitor download them. It is intended for collecting documents on the go
and retrieving them later from another computer, such as at a print shop.

The application runs on a host of type Mac. Files are added, renamed, organized,
and removed through the cloud-storage client; the web surface only lists and
downloads them.

## Canonical fields

### Application contract

- The source is a cloud-synced folder named `Outbox` on the Mac host.
- A lightweight file server exposes the folder through a browser.
- A reverse proxy maps the configured public URL to the file server.
- Directory listing and file download are supported.
- Uploading and file management through the browser are not supported.

### Deployment boundary

The app contract records only the portable behavior. Machine identity, network
addresses, filesystem paths, listener ports, process-supervisor configuration,
firewall rules, credentials, and log locations belong to deployment state and
are not part of this app-domain documentation.

### Operational boundaries

| Symptom | Owning boundary |
| --- | --- |
| A cloud file is missing or unavailable | Cloud synchronization or local materialization on the Mac host |
| The file server is unreachable from the proxy | Host networking, firewall, or the file-server process |
| The file server works directly but the URL fails | Reverse-proxy routing or public ingress |
| The service does not return after a restart | The Mac host's process supervisor |

## Known caveats

- The service is intentionally limited to listing and downloading files.
- Access control, when required, is owned by the ingress layer rather than this
  application.
