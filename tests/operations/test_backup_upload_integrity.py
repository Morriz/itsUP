from collections.abc import Iterable
from pathlib import Path
from typing import Any, BinaryIO
from urllib.parse import urlsplit

import boto3
import pytest
from botocore.awsrequest import AWSPreparedRequest, AWSResponse

from bin import backup, restore

SPEC_ID = "project/spec/feature/operations/backup-upload-integrity"
BUCKET = "backups"
COPY_SOURCE_HEADER = "x-amz-copy-source"


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


class _FakeRawStream:
    """Minimal stand-in for the urllib3 raw stream botocore reads responses from."""

    def __init__(self, body: bytes) -> None:
        self._body = body

    def stream(self, amt: int | None = None, decode_content: bool | None = None) -> Iterable[bytes]:
        yield self._body


def _fake_s3_response(status_code: int, headers: dict[str, str], body: bytes = b"") -> AWSResponse:
    return AWSResponse("https://s3.example.test/", status_code, headers, _FakeRawStream(body))


def _key_from_url(url: str, bucket: str) -> str:
    """Extract the object key from a path-style S3 request URL."""
    prefix = f"/{bucket}/"
    path = urlsplit(url).path
    assert path.startswith(prefix)
    return path[len(prefix) :]


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


@pytest.mark.functional
@pytest.mark.spec(SPEC_ID, "UC-BUI2")
def test_complete_upload_passes_verification_against_strict_s3_compatible_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """UC-BUI2: the staging upload request is unframed and the run publishes.

    Drives the real `backup.main` -> `upload_to_s3` -> `build_s3_client` chain
    against the real botocore client; only the HTTP transport is faked (a
    `before-send` handler on the client's event system), so the staging
    `PutObject` request this test inspects is the exact one botocore emits.
    """
    root = tmp_path / "root"
    (root / "upstream").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ITSUP_ROOT", str(root))

    def fake_load_secrets() -> dict[str, str]:
        return {
            "AWS_ACCESS_KEY_ID": "test-key",
            "AWS_SECRET_ACCESS_KEY": "test-secret",
            "AWS_S3_HOST": "s3.example.test",
            "AWS_S3_REGION": "us-east-1",
            "AWS_S3_BUCKET": BUCKET,
        }

    monkeypatch.setattr(backup, "load_secrets", fake_load_secrets)

    staging_requests: list[AWSPreparedRequest] = []
    marker_requests: list[AWSPreparedRequest] = []
    copy_requests: list[AWSPreparedRequest] = []
    delete_requests: list[AWSPreparedRequest] = []
    list_requests: list[AWSPreparedRequest] = []

    def before_send(request: AWSPreparedRequest, **kwargs: Any) -> AWSResponse:
        headers = request.headers
        if request.method == "PUT" and COPY_SOURCE_HEADER in headers:
            copy_requests.append(request)
            body = (
                b'<CopyObjectResult><ETag>"etag"</ETag>'
                b"<LastModified>2024-01-01T00:00:00.000Z</LastModified></CopyObjectResult>"
            )
            return _fake_s3_response(200, {}, body)
        if request.method == "PUT":
            key = _key_from_url(request.url, BUCKET)
            if key.startswith(backup.VALIDATED_PREFIX):
                marker_requests.append(request)
            else:
                staging_requests.append(request)
            return _fake_s3_response(200, {"ETag": '"etag"'})
        if request.method == "HEAD":
            content_length = staging_requests[0].headers.get("Content-Length")
            return _fake_s3_response(200, {"Content-Length": content_length})
        if request.method == "DELETE":
            delete_requests.append(request)
            return _fake_s3_response(204, {})
        if request.method == "GET":
            list_requests.append(request)
            body = (
                b'<?xml version="1.0" encoding="UTF-8"?>'
                b'<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
                b"<Name>backups</Name><KeyCount>0</KeyCount></ListBucketResult>"
            )
            return _fake_s3_response(200, {}, body)
        raise AssertionError(f"unexpected S3 request: {request.method} {request.url}")

    real_boto3_client = boto3.client

    def instrumented_client(service_name: str, *args: Any, **kwargs: Any) -> Any:
        client = real_boto3_client(service_name, *args, **kwargs)
        if service_name == "s3":
            client.meta.events.register("before-send.s3.*", before_send)
        return client

    monkeypatch.setattr(boto3, "client", instrumented_client)

    backup.main([])

    assert staging_requests, "the staging PutObject was never captured"
    staging_request = staging_requests[0]
    assert "aws-chunked" not in staging_request.headers.get("Content-Encoding", "")
    assert "X-Amz-Trailer" not in staging_request.headers
    content_length = staging_request.headers.get("Content-Length")
    assert content_length is not None
    assert content_length == str(len(staging_request.body))

    assert len(copy_requests) == 1
    assert len(marker_requests) == 1
    assert len(delete_requests) == 1
    assert len(list_requests) == 1
