---
description: Verified DigitalOcean Spaces S3-API compatibility facts for the itsUP backup/restore integration — CopyObject and UploadPartCopy are supported in-region (limited only across regions/clusters), plus ListObjectsV2, multipart upload, put/head/delete, and the 5GB single-copy threshold — grounding the staging→verify→server-side-copy upload path.
---

# DigitalOcean Spaces — S3 Compatibility (backup/restore integration)

Curated from the DigitalOcean Spaces S3 API reference
(`docs.digitalocean.com/reference/api/spaces/`) and the Spaces S3-compatibility page
(`docs.digitalocean.com/products/spaces/reference/s3-compatibility/`), read
2026-07-23, for the itsUP `bin/backup.py` / `bin/restore.py` S3 integration
(`AWS_S3_HOST=ams3.digitaloceanspaces.com`).

## Object operations relevant to backup/restore

- **`CopyObject` — supported** (Spaces API reference, "Object Operations"). The
  compatibility page states: "Supported with `CopyObject`. Cross-region and
  cross-cluster copies are not supported." So an in-region, same-bucket
  server-side copy is supported; only cross-region / cross-cluster copies are not.
- **`UploadPartCopy` — supported** (Spaces API reference, "Advanced Object
  Uploads": "Uploads a part by copying data from an existing object"). The
  compatibility page's note, "`UploadPartCopy` is not supported across regions or
  clusters," scopes the limitation to cross-region/cluster only — parallel to the
  `CopyObject` wording — so in-region multipart server-side copy is supported.
- **`ListObjectsV2` — supported** ("Both `ListObjects` (legacy) and `ListObjectsV2`
  are supported").
- **Multipart uploads — supported** for large objects.
- **`PutObject`, `HeadObject`, `DeleteObject`** — core object operations, already
  exercised by the existing itsUP backup (`upload_fileobj`, `delete_object`) and
  restore (`download_file`) paths against this endpoint.

## Size threshold

- A single `CopyObject` is an atomic server-side copy for objects **up to 5GB**
  (standard S3 semantics). Objects larger than 5GB must be copied server-side via
  the multipart `UploadPartCopy` API — which Spaces supports in-region.

## Implication for the itsUP upload path

- The backup staging key and final generation key live in the **same bucket and
  region**, so promotion is an **in-region** copy and is supported at **any archive
  size**.
- boto3's managed **`s3_client.copy`** is the correct promotion call: it performs a
  single `CopyObject` below the multipart threshold and an in-region
  `UploadPartCopy` multipart copy above it — both supported on Spaces. The low-level
  `copy_object` is single-op-only (≤5GB); the managed `copy` removes that ceiling
  without hitting the unsupported cross-region path.

## Sources

- https://docs.digitalocean.com/reference/api/spaces/ — Spaces API reference (CopyObject under Object Operations; UploadPartCopy under Advanced Object Uploads).
- https://docs.digitalocean.com/products/spaces/reference/s3-compatibility/ — Spaces S3 compatibility (cross-region/cluster copy limitation; ListObjectsV2 and multipart upload support).
- https://docs.aws.amazon.com/AmazonS3/latest/API/API_CopyObject.html — CopyObject 5GB single-operation limit.
