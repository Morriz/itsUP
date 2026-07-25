---
description: Verified botocore/boto3 S3 request-checksum behavior for the itsUP backup/restore integration — the ≥1.36 default (request_checksum_calculation=when_supported) frames PutObject/upload as aws-chunked with a STREAMING-UNSIGNED-PAYLOAD-TRAILER CRC32 trailer, which many S3-compatible providers (incl. DigitalOcean Spaces) mis-store, and request_checksum_calculation=when_required disables it; includes the pinned-version verification that the managed upload_fileobj path honors when_required on botocore 1.43.55.
---

# botocore/boto3 — S3 request-checksum integrity (backup/restore integration)

Curated for the itsUP `bin/backup.py` / `bin/restore.py` S3 integration against
DigitalOcean Spaces (`AWS_S3_HOST=ams3.digitaloceanspaces.com`). Read 2026-07-25.
Pairs with `third-party/digitalocean-spaces/s3-compatibility` (provider-side
object-operation support).

## The ≥1.36 default data-integrity change

- **botocore 1.36.0 (Jan 2025) enabled default request checksums for S3.**
  For upload-shaped operations (`PutObject`, `UploadPart`) the SDK now computes a
  CRC32 checksum by default and attaches it, controlled by
  `request_checksum_calculation` — a `botocore.config.Config` argument, a shared
  AWS-config key, or the `AWS_REQUEST_CHECKSUM_CALCULATION` environment variable.
  Its two values are `when_supported` (the new default) and `when_required`.
- **`when_supported` frames the upload as aws-chunked with a streaming trailer.**
  The request carries `Content-Encoding: aws-chunked`,
  `X-Amz-Content-SHA256: STREAMING-UNSIGNED-PAYLOAD-TRAILER`,
  `X-Amz-Trailer: x-amz-checksum-crc32`, and
  `x-amz-sdk-checksum-algorithm: CRC32`; the body is chunk-framed with a trailing
  checksum (botocore wraps it in an `AwsChunkedWrapper`) and no fixed
  `Content-Length`.

## S3-compatible-provider incompatibility

- Many non-AWS S3-compatible services do not support the aws-chunked
  streaming-trailer checksum encoding on `PutObject`, and either reject the
  request (`Unsupported header 'x-amz-sdk-checksum-algorithm'`) or **mis-store the
  object** so its persisted length no longer matches the sent bytes. Reported
  across Backblaze B2, SeaweedFS, Google Cloud Storage, and DigitalOcean Spaces
  after boto3/botocore ≥1.36.
- **Remedy: `request_checksum_calculation="when_required"`.** It suppresses the
  default calculation for calls that do not themselves require a checksum, so the
  upload is sent as a plain body the provider stores verbatim.
- **Version caveat.** Early after the change, the managed-transfer path
  (`s3transfer`, i.e. `upload_file`/`upload_fileobj` and `aws s3 cp`) did **not**
  honor `when_required` on some versions (s3transfer #327). The setting must be
  verified against the pinned version rather than assumed.

## Pinned-version verification (itsUP)

On the itsUP-pinned `botocore` / `boto3` **1.43.55**, the managed
`upload_fileobj` path — the exact call `bin/backup.py` uses — honors
`request_checksum_calculation="when_required"`:

- **Default `Config(signature_version="s3v4")`:** the emitted `PutObject` carries
  `Content-Encoding: aws-chunked`, `X-Amz-Content-SHA256:
  STREAMING-UNSIGNED-PAYLOAD-TRAILER`, `X-Amz-Trailer: x-amz-checksum-crc32`, body
  wrapped in `AwsChunkedWrapper`, no fixed `Content-Length`.
- **`Config(signature_version="s3v4", request_checksum_calculation="when_required")`:**
  the emitted `PutObject` carries no `Content-Encoding: aws-chunked`, no
  `X-Amz-Trailer`, a real content SHA256, and `Content-Length: 55` for a 55-byte
  body — a plain upload a strict S3-compatible provider stores verbatim.

So on this version `when_required` is sufficient to remove the framing on the real
upload path; `response_checksum_validation` (download side) is a separate setting
not exercised by the upload flow.

## Sources

- https://github.com/boto/boto3/issues/4392 — "Announcement: S3 default integrity change" (the ≥1.36 default; `request_checksum_calculation` / `AWS_REQUEST_CHECKSUM_CALCULATION`; `when_supported`/`when_required`).
- https://github.com/boto/boto3/discussions/4712 — checksums + aws-chunked encoding emitted for S3 uploads; the `STREAMING-UNSIGNED-PAYLOAD-TRAILER` framing.
- https://github.com/seaweedfs/seaweedfs/issues/6548 — incorrect upload to an S3-compatible store with boto3 ≥1.36.0 (provider mis-store symptom).
- https://github.com/boto/s3transfer/issues/327 — `aws s3 cp` / managed transfer not honoring `request_checksum_calculation=when_required` on affected versions (the version caveat).
- https://docs.digitalocean.com/products/spaces/how-to/use-aws-sdks/ — DigitalOcean Spaces AWS-SDK usage reference.
- https://www.beginswithdata.com/2025/05/14/aws-s3-tools-with-gcs/ — S3-compatible (GCS) breakage under the same default change and the `when_required` mitigation.
