from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import ALLOWED_FILE_CONTENT_TYPES, app

SPEC_ID = "project/spec/feature/api/gated-file-serving"
FILE_BYTES = b'{"rules": []}'


@pytest.mark.functional
@pytest.mark.spec(SPEC_ID, "UC-GFS1")
def test_file_endpoint_serves_allowlisted_file_with_its_mapped_content_type(tmp_path: Path) -> None:
    allowed_file = tmp_path / "rules.lsrules"
    allowed_file.write_bytes(FILE_BYTES)

    response = TestClient(app).get("/file", params={"path": str(allowed_file)})

    assert response.status_code == 200
    assert response.content == FILE_BYTES
    assert response.headers["content-type"] == ALLOWED_FILE_CONTENT_TYPES[allowed_file.suffix]


@pytest.mark.functional
@pytest.mark.spec(SPEC_ID, "UC-GFS2")
def test_file_endpoint_refuses_non_allowlisted_extension(tmp_path: Path) -> None:
    non_allowlisted_file = tmp_path / "settings.json"
    non_allowlisted_file.write_bytes(FILE_BYTES)

    response = TestClient(app).get("/file", params={"path": str(non_allowlisted_file)})

    assert response.status_code == 403
    assert response.content != FILE_BYTES


@pytest.mark.functional
@pytest.mark.spec(SPEC_ID, "UC-GFS3")
def test_file_endpoint_refuses_missing_allowlisted_file(tmp_path: Path) -> None:
    missing_file = tmp_path / "missing.lsrules"

    response = TestClient(app).get("/file", params={"path": str(missing_file)})

    assert response.status_code == 404
