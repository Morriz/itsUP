---
description: launchctl verbs itsUP's macOS API supervision depends on — bootstrap/bootout as load/unload of a job in a domain, and kickstart -k as the launchd-owned restart that a process may safely request against its own job.
---

# launchd — Agent Lifecycle Verbs

## What it is

itsUP supervises its API server on macOS as a launchd user agent, and the API's
self-update path has to restart that agent from inside the very process the
agent supervises. Which verb is used decides whether that works: a
`bootout`-then-`bootstrap` pair asks the terminated process to complete the
reload, while `kickstart -k` hands the whole restart to launchd. The repository
already uses `bootstrap`/`bootout` for install and teardown, so both verbs are
in play and the distinction has to be explicit.

## Canonical fields

### `kickstart` — run now, optionally killing the running instance first

> kickstart [-kp] service-target
>
> Instructs launchd to run the specified service immediately, regardless of its
> configured launch conditions.
>
> -k  If the service is already running, kill the running instance before
> restarting the service.
>
> -p  Upon success, print the PID of the new process or the already-running
> process to stdout.

`kickstart -k` is a single request to launchd: it kills the current instance and
starts a new one. The restart is executed by launchd, not by the caller, so the
caller's own termination does not abort it.

### `bootstrap` / `bootout` — load and unload a job in a domain

`bootstrap <domain> <plist>` loads a job into a domain; `bootout <domain>
<plist>` (or `bootout <domain>/<label>`) unloads it. Unloading terminates the
job's process. These are the install/uninstall verbs — they change whether
launchd knows about the job at all.

`bootout` followed by `bootstrap` is therefore **not** a restart primitive: it is
an unload followed by a separate load. The two are independent requests.

### Why the distinction is load-bearing for self-restart

A process that runs `bootout` against its own job is terminated as a direct
result of that call. Any subsequent `bootstrap` in the same script or the same
process never executes, because the caller no longer exists. The job ends up
unloaded rather than restarted, and nothing on the host brings it back until the
agent is loaded again.

`kickstart -k` has no such window: launchd holds the restart, and the caller's
death is expected rather than fatal to the operation.

### `KeepAlive` respawns a crash, but does not undo an unload

`KeepAlive` governs whether launchd restarts a job that exits. It does not
re-load a job that was booted out — `bootout` removes the job from the domain,
so there is nothing left for `KeepAlive` to act on.

## Known caveats

- **`bootout` + `bootstrap` reads like a restart and is not one.** It is the
  most common way to leave a self-restarting macOS agent permanently unloaded.
  Use it for install/uninstall; use `kickstart -k` for restart.
- **`KeepAlive` is not a safety net for a bad restart verb.** It covers crashes
  and clean exits of a *loaded* job only.
- **A service-target is domain-qualified.** The GUI domain for a user agent is
  `gui/<uid>`, so the restart target is `gui/<uid>/<label>` — the same domain
  form the install and teardown paths already use.

## Sources

- https://keith.github.io/xcode-man-pages/launchctl.1.html
