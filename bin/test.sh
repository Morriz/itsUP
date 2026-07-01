#!/usr/bin/env sh
. .venv/bin/activate

# Fast tier only: pytest's default addopts exclude the `integration` marker.
# The integration tier (real sops/age/git) runs via `make test-integration` / CI.
pytest
