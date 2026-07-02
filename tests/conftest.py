import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest


@pytest.fixture
def isolated_itsup_root(monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        monkeypatch.setenv("ITSUP_ROOT", str(root))
        yield root
