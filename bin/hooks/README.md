# Git hooks (opt-in)

This directory holds git hooks used by the project.

Enable them in your clone:

```bash
git config core.hooksPath bin/hooks
```

Hooks:

These hooks are TeleClaude-owned (refreshed from the platform's hook templates
by project-plumbing convergence — see `teleclaude.yml`'s `checkpoint`
overlay and `~/.teleclaude/docs` for `project/spec/feature/reconciliation/project-plumbing-convergence`);
edit the templates upstream, not the files here.

- `pre-commit`: partial-staging guard; delegates to `telec code pre-commit`.
- `post-commit`: runs deterministic post-commit maintenance via
  `telec code post-commit` — for this project, `checkpoint.maintenance.deps`
  (`uv sync`) when `pyproject.toml`/`uv.lock` changed.
- `post-merge`: runs the same deterministic maintenance via
  `telec code post-merge`, so a merge that changes `pyproject.toml`/`uv.lock`
  also triggers `uv sync`.
- `pre-push`: blocks a push to `main` from outside the canonical checkout or
  the integration worktree (`telec code`-backed guard).
