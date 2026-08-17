# ADR 0009 — Durable Prediction-Image Storage Boundary

- Status: Accepted
- Date: 2026-08-17

## Context

Prediction creation previously persisted a local `uploads/<filename>` path and
the worker treated that database value as a host filesystem path. That coupled
the API, database, worker, and deployment filesystem, prevented an object-store
backend from replacing local storage, and made the path itself an implicit
cross-component contract.

VDDAI needs an explicit boundary without provisioning S3/MinIO or changing the
frozen inference, preprocessing, queue, authentication, or public API contracts.

## Decision

`ImageStorageService` validates uploads and generates opaque keys in the form
`predictions/<uuid>.<validated-extension>`. The multipart filename is never
used to choose a key or destination. The service delegates object operations to
an `ImageObjectStore` contract with write, read, delete, and existence checks.

The configured v0.1 implementation is `LocalFilesystemImageObjectStore`, rooted
at `IMAGE_STORAGE_ROOT`. It maps validated key components below that root,
rejects absolute, traversal, backslash, drive-qualified, malformed, and
root-escaping keys, and keeps resolved paths inside the backend. Deleting an
already-missing object is an idempotent no-op reported as `false`.

The API persists only the returned key. The worker passes that key to the
storage service, receives bytes, and supplies those bytes to the existing
preprocessing and inference path. API and worker orchestration therefore do not
change when another backend implements the same object operations. No S3/MinIO
service, SDK, bucket, or credential is added by this decision.

The physical database column remains `predictions.image_path` to preserve the
schema and data. The SQLAlchemy attribute is `image_object_key`, and all newly
created rows store opaque keys rather than filesystem paths. No Alembic
migration is justified solely to rename the physical column. Historical rows
are not rewritten or deleted; terminal history remains readable, while an old
queued row whose value names a local path will fail safely unless an operator
migrates its object and value to the configured backend.

The frozen `vddai.preprocessing.rgb_chw_bilinear.v1` source label is retained.
Storage lookup occurs before preprocessing and does not change EXIF handling,
RGB conversion, resize policy, tensor shape/layout/dtype/range, normalization
ownership, scorer behavior, threshold equality, lineage, or public failure
semantics.

## Retention and Failure Policy

Uploaded inputs are retained for the prediction-history lifetime. A successful
or failed inference does not delete its input. VDDAI currently has no public
prediction-delete endpoint, record-coupled deletion, retention scheduler, or
automatic garbage collector; platform operations owns intentional deletion.

| Event | Required behavior |
|---|---|
| Storage write fails | Return the existing safe upload-storage error and create no prediction row. |
| Database commit fails after storage | Roll back, attempt `delete(object_key)`, log cleanup failure, and re-raise the original database error. |
| Worker read finds a missing or unreadable object | Preserve the normal claim transaction, then persist the stable safe `inference_failed` terminal state where recovery permits. |
| Deletion targets an absent object | Return `false`; repeated deletion remains safe. |
| Prediction reaches a terminal state | Retain the input object until an explicit retention or record-deletion operation owns removal. |

The request path knows the exact newly written key and performs deterministic
best-effort cleanup immediately after a database failure. Any object left by a
cleanup failure is an orphan. Operators can identify older orphans by comparing
the backend inventory under `predictions/` with the keys referenced by the
physical `predictions.image_path` column, then call the idempotent delete
operation for unreferenced keys. Automated inventory and scheduling are
intentionally deferred.

## Consequences

- Database values no longer disclose or depend on a local storage root.
- API and worker code are backend-independent and local paths remain a local
  implementation detail.
- Local development and tests need only a configured temporary/root directory.
- Multi-instance production still requires provisioning and implementing a
  shared object-storage backend plus operational retention automation.
- Pre-boundary queued rows containing filesystem paths require explicit
  operator migration or will fail closed; no unsafe path fallback is provided.
