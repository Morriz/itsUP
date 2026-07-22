---
description: launchctl verbs itsUP's macOS API supervision depends on — bootstrap/bootout as load/unload of a job in a domain, and kickstart -k as the launchd-owned restart that a process may safely request against its own job.
---

# launchd — Agent Lifecycle Verbs

## What it is

`bin/install-bringup.sh` and `bin/uninstall-runtime.sh` already drive launchd
agents with `bootstrap` and `bootout`. Any design that adds a **resident** agent
— one supervised for crashes, or one a process might restart from inside itself
— depends on distinctions those two verbs do not make: which verb starts an
unloaded job, which restarts a loaded one, and whether opting into crash
supervision also opts into starting at load. This entry records those launchd
contracts verbatim so a design can be checked against them rather than against
an assumption.

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

### Any `KeepAlive` implies `RunAtLoad` — a supervised job self-starts on load

> KeepAlive <boolean or dictionary of stuff>
>
> This optional key is used to control whether your job is to be kept
> continuously running or to let demand and conditions control the invocation.
> The default is false and therefore only demand will start the job. ... **The
> use of this key implicitly implies RunAtLoad, causing launchd to
> speculatively launch the job.**

The dictionary form carries the same implication, and `SuccessfulExit` states it
again explicitly:

> SuccessfulExit <boolean>
>
> ... This key implies that "RunAtLoad" is set to true, since the job needs to
> run at least once before an exit status can be determined.

So **omitting `RunAtLoad` does not make a `KeepAlive` job demand-only.** Any job
that opts into crash supervision starts the moment it is bootstrapped into the
domain. There is no plist shape that gives crash-restart without load-time
activation.

The consequence for orchestration: on macOS, `bootstrap` **is** a start. There is
no *plist-level* equivalent of installing a systemd unit without enabling it — no
key gives crash supervision while withholding load-time activation.

The separation is still available, one level up: **writing a plist and
bootstrapping it are separate acts.** An installer can render the plist to
`~/Library/LaunchAgents` and stop there; whoever later runs `bootstrap` is the
job's starter. So an orchestrator that wants to own startup does not fight
`KeepAlive` — it declines to bootstrap, and performs the bootstrap itself at the
point in its sequence where the job belongs.

Because `bootstrap` starts the job, it is also the correct **start** verb for a
job that is not loaded, and `bootout` the correct **stop** verb — `kickstart`
requires an already-loaded job and cannot recover one that was booted out.

## Known caveats

- **`bootout` + `bootstrap` in one breath reads like a restart and is not one.**
  A process that boots out its own job never reaches the bootstrap. Use
  `kickstart -k` when the job is loaded; use the two verbs separately as stop
  and start.
- **`kickstart` cannot start an unloaded job.** Pairing `bootout` as stop with
  `kickstart` as start yields a service that stops once and never starts again.
  Start must be `bootstrap` whenever the job may be unloaded.
- **`KeepAlive` is not a safety net for a bad restart verb.** It covers crashes
  and clean exits of a *loaded* job only.
- **Reading only the first half of the `KeepAlive` entry inverts its meaning.**
  The paragraph opens with "The default is false and therefore only demand will
  start the job" — describing the key's *absence* — and closes with the
  implicit-`RunAtLoad` implication that governs its *presence*. Quoting the
  opening as evidence that a `KeepAlive` job stays demand-only is a
  contract-fidelity error.
- **A service-target is domain-qualified.** The GUI domain for a user agent is
  `gui/<uid>`, so the restart target is `gui/<uid>/<label>` — the same domain
  form the install and teardown paths already use.

## Sources

- https://keith.github.io/xcode-man-pages/launchctl.1.html
