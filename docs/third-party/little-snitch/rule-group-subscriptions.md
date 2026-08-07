---
description: Verified Little Snitch rule-group subscription contract for itsUP's .lsrules serving path — the mandatory HTTPS publication requirement, the .lsrules JSON shape, the subscriber-owned update interval, the x-littlesnitch:subscribe-rules deep link, and the caching/content-type contract the vendor documents nowhere.
---

# Little Snitch — Rule Group Subscriptions

## What it is

A Little Snitch **rule group subscription** is a named group of firewall rules
the app fetches from a URL and refreshes on a schedule. The publisher's entire
obligation is to make one `.lsrules` file reachable over HTTPS; everything about
when and how often it is fetched is configured on the subscriber's machine.

itsUP serves such a file from `GET /file?path=…`
(`project/spec/feature/api/gated-file-serving`), which is why this contract
matters: it bounds what the server side can and cannot influence.

## Publishing requirements (the whole server-side contract)

Objective Development states publishing needs exactly two things: the rules in a
`.lsrules` file, and *"a web server that is accessible via HTTPS"*.

- **HTTPS is mandatory, not advisory.** *"For security reasons, Little Snitch
  requires that rule groups are published via HTTPS. Unencrypted HTTP
  connections are not supported."* A plain-HTTP URL is not a usable subscription
  URL at all.
- The file may be produced by exporting from Little Snitch Configuration **or**
  *"by creating the `.lsrules` file using a text editor or a script"* — machine
  generation is an explicitly supported authoring path.
- No other server-side requirement is stated.

## The `.lsrules` file format

JSON. Top-level keys:

| Key | Required | Meaning |
|---|---|---|
| `name` | yes | Group identifier shown to the subscriber |
| `description` | yes | Group explanation shown to the subscriber |
| `rules` | no | Array of full rule objects |
| `denied-remote-domains` | no | Compact blocklist shortcut (Little Snitch 4.2+) |
| `denied-remote-hosts` | no | Compact blocklist shortcut |
| `denied-remote-addresses` | no | Compact blocklist shortcut |
| `denied-remote-notes` | no | Shared note for the shortcut rules; supports the `%REMOTE%` placeholder |

The `rules` array and the `denied-remote-*` shortcuts may be mixed in one file.
A rule object carries `process` with an optional `via`, one remote selector
(`remote-addresses` / `remote-hosts` / `remote-domains` / `remote`), and optional
`direction`, `action`, `priority`, `disabled`, `ports`, `protocol`, `notes`.

`process` accepts three forms: `"any"`, an absolute executable path
(*"path based rules"*), or a **code ID** given as
`identifier.DEV_TEAM_ID/IDENTIFIER` — the vendor's own example being
`identifier.MLZF7K7B5R/at.obdev.littlesnitch`. The code-ID form binds a rule to a
signed application's identity rather than its location on disk.

## Subscribing and refreshing

- A subscription is added in Little Snitch Configuration via
  **File → New Rule Group Subscription**, entering the group's URL.
- The **subscriber** chooses the update interval at which Little Snitch connects
  to the publisher's server and checks for updates. The publisher has no input
  into it, and *"subscribers may choose to disable automatic updates"* entirely —
  the vendor warns publishers not to expect a modification to reach every
  subscriber.
- When an update adds or modifies rules *"in a way that affects what connections
  it allows or denies"*, Little Snitch notifies the user and marks the affected
  rules unapproved for review.

## Deep link

A publisher may offer a clickable link that opens Little Snitch Configuration
with the URL pre-filled:

```
x-littlesnitch:subscribe-rules?url=https%3A%2F%2Fexample.com%2FSomeRules.lsrules
```

The subscription URL is a query parameter and therefore **must be
percent-encoded**. A subscription URL that itself carries a query string (as
itsUP's `?path=…` does) is unaffected as a plain URL, but its `?` and `&` must be
encoded when embedded in this deep link.

## What the vendor does NOT specify

Checked across the Little Snitch 4, 5, and 6 help sets (`ref-lsrules-file-format`
/ `adv-lsrules-file-format` and `lsc-rule-group-subscriptions`). None of the
following appears anywhere in the published contract:

- **No required `Content-Type`.** The vendor never names a MIME type for
  `.lsrules`. Serving it as `application/json` is consistent with the format
  being JSON but is not a documented requirement.
- **No `Content-Disposition` requirement.** The subscription fetcher is Little
  Snitch itself, not a browser, so nothing is "rendered inline" on the
  subscription path. A disposition header only affects a human who opens the URL
  in a browser.
- **No caching contract.** `ETag`, `Last-Modified`, `Content-Length`, and
  conditional requests are never mentioned. Whether the client issues a
  conditional GET, and what it keys a re-fetch on, is unspecified by the vendor.
- **No server-side change signal.** There is no documented way for a publisher to
  tell subscribers that the group changed; refresh is polling on the subscriber's
  interval, full stop.

Consequence for itsUP: an observation that the client re-fetches only when the
file changes is **client behavior over an ordinary HTTP GET**, not a contract the
server is required to implement or is able to guarantee. The server's obligations
end at a stable HTTPS URL returning valid `.lsrules` JSON. See
`third-party/starlette/fileresponse-caching-headers` for the validators the
serving path already emits.

## Sources

- [Rule group subscriptions — Little Snitch 5 Help](https://help.obdev.at/littlesnitch5/lsc-rule-group-subscriptions)
- [The .lsrules file format — Little Snitch 5 Help](https://help.obdev.at/littlesnitch5/ref-lsrules-file-format)
- [The .lsrules file format — Little Snitch 6 Help](https://help.obdev.at/littlesnitch6/adv-lsrules-file-format)
- [Rule group subscriptions — Little Snitch 4 Help](https://help.obdev.at/littlesnitch4/lsc-rule-group-subscriptions)
