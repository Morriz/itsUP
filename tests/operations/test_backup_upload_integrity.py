from collections.abc import Iterable
from pathlib import Path
from typing import BinaryIO

import pytest

from bin import backup, restore

SPEC_ID = "project/spec/feature/operations/backup-upload-integrity"
BUCKET = "backups"


class FakeS3:
    """In-memory S3 boundary fake with controllable upload completeness."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.uploaded_length: int | None = None

    def list_objects_v2(self, *, Bucket: str) -> dict[str, list[dict[str, str]]]:
        assert Bucket == BUCKET
        return {"Contents": [{"Key": key} for key in sorted(self.objects)]}

    def upload_fileobj(self, file_data: BinaryIO, bucket: str, key: str) -> None:
        assert bucket == BUCKET
        archive = file_data.read()
        stored_length = len(archive) if self.uploaded_length is None else self.uploaded_length
        self.objects[key] = archive[:stored_length]

    def head_object(self, *, Bucket: str, Key: str) -> dict[str, int]:
        assert Bucket == BUCKET
        return {"ContentLength": len(self.objects[Key])}

    def put_object(self, *, Bucket: str, Key: str, Body: bytes) -> None:
        assert Bucket == BUCKET
        self.objects[Key] = Body

    def copy(self, *, CopySource: dict[str, str], Bucket: str, Key: str) -> None:
        assert Bucket == BUCKET
        assert CopySource["Bucket"] == BUCKET
        self.objects[Key] = self.objects[CopySource["Key"]]

    def delete_object(self, *, Bucket: str, Key: str) -> None:
        assert Bucket == BUCKET
        self.objects.pop(Key, None)


def _validated_generations(client: FakeS3) -> set[str]:
    """Return the generation keys currently accompanied by validation markers."""
    return {
        key
        for key in client.objects
        if key.startswith(f"{backup.DB_FILE}.") and f"{backup.VALIDATED_PREFIX}{key}" in client.objects
    }


def _seed_validated_generations(client: FakeS3, timestamps: Iterable[str]) -> set[str]:
    """Seed complete legacy-independent restore points with validation markers."""
    generations = {f"{backup.DB_FILE}.{timestamp}" for timestamp in timestamps}
    for generation in generations:
        client.objects[generation] = b"complete archive"
        client.objects[f"{backup.VALIDATED_PREFIX}{generation}"] = b""
    return generations


@pytest.mark.functional
@pytest.mark.spec(SPEC_ID, "UC-BUI1")
def test_incomplete_upload_never_publishes_or_displaces_validated_backups(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """UC-BUI1: a failed upload never becomes a restore point or prunes one."""
    root = tmp_path / "root"
    (root / "upstream").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ITSUP_ROOT", str(root))

    s3_client = FakeS3()
    seeded_generations = _seed_validated_generations(
        s3_client,
        (f"20240101{index:04d}" for index in range(11)),
    )

    def build_test_client() -> tuple[FakeS3, str]:
        return s3_client, BUCKET

    monkeypatch.setattr(backup, "build_s3_client", build_test_client)
    s3_client.uploaded_length = 1
    objects_before_failed_upload = dict(s3_client.objects)

    with pytest.raises(SystemExit) as failed_upload:
        backup.main([])

    assert failed_upload.value.code != 0
    assert s3_client.objects == objects_before_failed_upload

    s3_client.uploaded_length = None
    backup.main([])

    validated_after_success = _validated_generations(s3_client)
    assert len(validated_after_success) == 10
    assert {key for key in s3_client.objects if key.startswith(f"{backup.DB_FILE}.")} == validated_after_success
    assert len(validated_after_success - seeded_generations) == 1

    unvalidated_generation = f"{backup.DB_FILE}.20990101000000"
    s3_client.objects[unvalidated_generation] = b"incomplete archive"
    backup.main([])

    validated_after_retention = _validated_generations(s3_client)
    assert unvalidated_generation not in s3_client.objects
    assert len(validated_after_retention) == 10
    assert {key for key in s3_client.objects if key.startswith(f"{backup.DB_FILE}.")} == validated_after_retention

    monkeypatch.setattr(restore, "build_s3_client", build_test_client)
    capsys.readouterr()
    restore.main(["all", "--list"])

    assert capsys.readouterr().out.splitlines() == sorted(validated_after_retention, reverse=True)
