"""Root pytest configuration: test-tier marking for the whole suite."""

from pathlib import Path

import pytest

_INTEGRATION_SUITE = Path(__file__).parent / "tests" / "functional"


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Mark the real-boundary suite (real sops/age/git) as integration.

    Tier selection is by marker, not directory: this stamps the ``integration``
    marker onto every test under ``tests/functional`` so the fast gate's
    ``-m "not integration"`` deselection excludes it. Runs ``tryfirst`` so the
    marker is present before pytest applies that deselection.
    """
    for item in items:
        if _INTEGRATION_SUITE in Path(str(item.fspath)).parents:
            item.add_marker(pytest.mark.integration)
