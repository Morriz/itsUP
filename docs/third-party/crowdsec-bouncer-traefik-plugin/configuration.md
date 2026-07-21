---
description: Verified configuration semantics of the maxlerebourg crowdsec-bouncer-traefik-plugin — client-IP trust and bypass options (clientTrustedIPs, forwardedHeadersTrustedIPs), operating modes, AppSec flags, and LAPI wiring — for the entrypoint-level enforcement attachment.
---

# CrowdSec Bouncer Traefik Plugin — Configuration Reference

Curated from the official plugin repository
(`github.com/maxlerebourg/crowdsec-bouncer-traefik-plugin`, read 2026-07-21).
itsUP pins plugin `v1.6.0` (`tpl/traefik.yml.j2` `experimental.plugins.bouncer`
and the middleware's `version` field). The options below are stable across
recent plugin versions.

## Client-IP trust and bypass

- `clientTrustedIPs` (default `[]`) — "List of client IPs to trust, they will
  bypass any check from the bouncer or cache (useful for LAN or VPN IP)."
  Requests originating from these addresses skip all remediation: a CrowdSec
  decision against such an IP is never enforced. This is the mass-ban guard —
  listing the router IP and the private ranges makes internal/LAN traffic
  unbannable even if client-IP resolution degrades to a shared upstream
  address.
- `forwardedHeadersTrustedIPs` (default `[]`) — "List of IPs of trusted
  Proxies that are in front of traefik (ex: Cloudflare)." Only when the
  direct peer is in this list does the plugin honor forwarded headers to
  extract the real client IP; the header name is `forwardedHeadersCustomName`
  (default `X-Forwarded-For`).

## Activation and modes

- `enabled` (default `false`) — enables the plugin's remediation logic. A
  middleware definition with `enabled: false` still instantiates but performs
  no checks. Instantiation happens only when some router chain or entrypoint
  `http.middlewares` references the middleware — an unreferenced definition
  is valid config and fully inert (no LAPI polling, no enforcement).
- `crowdsecMode` (default `live`) — one of `none`, `live`, `stream`, `alone`,
  `appsec`. `live` queries the LAPI per unknown IP and caches; `stream` pulls
  the decision set on an interval (upstream recommends it for performance).

## AppSec (WAF)

- `crowdsecAppsecEnabled` (default `false`) — routes requests through the
  CrowdSec AppSec component for WAF inspection beyond IP reputation.
- `crowdsecAppsecFailureBlock` (default `true`) — blocks the request when the
  AppSec server answers HTTP 500.

## LAPI wiring

- `crowdsecLapiKey` (default empty) — bouncer API key, generated via
  `cscli bouncers add` (itsUP injects `${CROWDSEC_APIKEY}`).
- `crowdsecLapiHost` (default `crowdsec:8080`) — LAPI address (itsUP:
  `127.0.0.1:18080`, host-networked crowdsec container).

## Sources

- https://github.com/maxlerebourg/crowdsec-bouncer-traefik-plugin (official
  README, options table and defaults)
