# Git hooks (opt-in)

This directory holds git hooks used by the project.

Enable them in your clone:

```bash
git config core.hooksPath bin/hooks
```

Hooks:
- `post-merge`: if any `requirements*.txt` changed between previous and current HEAD, runs `.venv/bin/pip install -r ...` for the changed files.
