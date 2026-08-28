# VDDAI System Requirements

- Status: Current
- Last reviewed: 2026-08-21
- Scope: v0.1 visual-inspection feasibility-pilot platform

## Product Boundary

VDDAI must support one constrained inspection project and one explicitly
configured model package at a time. It must not claim universal defect
detection, safety-certified automated rejection, or customer validation from
public benchmark results.

## Functional Requirements

- Authenticate users with bearer JWTs and reject inactive users.
- Accept encoded-size-limited and decoded-pixel-limited JPEG, PNG, and WebP
  uploads after structural decoding and media-type validation.
- Bound application upload reads to the configured maximum plus one byte and
  reject oversized uploads before image decoding or storage.
- Reject images above the configured decoded-pixel budget before object storage
  and before decode-heavy online or offline preprocessing. Permit configuration
  to lower but never raise the approved 16,777,216-pixel ceiling.
- Rate-limit authenticated prediction submissions per user and cap per-user
  and service-wide outstanding work with explicit retryable failures.
- Generate opaque server-controlled image object keys and owner-scoped
  prediction records.
- Process predictions asynchronously through the database-backed worker queue.
- Treat every accepted prediction submission as a distinct job while making
  execution of each persisted job replay-safe.
- Return prediction lifecycle state and safe completed-result fields.
- Preserve prediction history and the exact model-package lineage used for each
  successful result.

## Security and Privacy Requirements

- Derive ownership from the authenticated identity, never from request input.
- Prevent ordinary users from accessing another user's predictions.
- Keep internal paths, secrets, password hashes, stack traces, and private model
  artifacts out of public responses.
- Resolve prediction image objects only through the configured storage backend;
  never interpret request filenames or persisted keys as trusted host paths.
- Preserve non-disclosing not-found behavior for unauthorized prediction reads.

## ML Integrity Requirements

- Fit feature banks with normal training records only.
- Select thresholds with normal validation records only.
- Keep the official test split isolated from model, scorer, hyperparameter, and
  threshold selection.
- Use the same storage-level preprocessing contract offline and online.
- Apply ImageNet normalization exactly once inside the frozen ResNet-18
  extractor.
- Preserve higher-is-more-anomalous scoring and strict `score > threshold`
  classification.
- Fail closed on missing, corrupt, incompatible, or lineage-incomplete packages.

## Persistence and Worker Requirements

- Apply persistent schema changes through Alembic.
- Keep transaction ownership explicit and roll back failed units of work.
- Serialize prediction count-and-insert admission through PostgreSQL so
  simultaneous API requests cannot exceed configured outstanding limits.
- Count `queued` and `processing` predictions as outstanding while excluding
  all terminal states, including `needs_review`.
- Prevent concurrent workers from claiming the same queued row.
- Commit a bounded lease and monotonically increasing attempt token before
  inference, without holding a database transaction during inference.
- Recover expired or legacy lease-less processing work after worker restart and
  enforce a finite, positive, bounded retry policy.
- Permit at-least-once computation while allowing only the current attempt to
  persist an authoritative terminal transition.
- Retrieve claimed prediction inputs through the image-storage contract and
  fail safely when an object is missing or unreadable.
- Persist successful result fields atomically with the terminal lifecycle state.
- Persist a safe terminal failure where recovery permits, while keeping internal
  diagnostics out of the public API.

## Reproducibility and Audit Requirements

- Pin Python and project dependencies.
- Record dataset identity, code revision, effective parameters, seeds, metrics,
  artifact locations, checksums, schema versions, and terminal experiment state.
- Keep experiment recording, candidate registration, promotion, and serving
  resolution as separate auditable operations.
- Require explicit human approval for production model promotion or rollback.

## Operational Requirements

- Support local development and the documented Docker Compose stack.
- Provide a traversal-safe local image-storage backend while keeping API and
  worker orchestration compatible with a future object-storage backend.
- Validate exact dependency versions, documentation structure, one Alembic
  head, changed-Python formatting, the complete test suite with PostgreSQL 16,
  strict production-regression evidence, Compose wiring, and application-image
  construction through the hosted repository quality gate.
- Treat failed, skipped, canceled, timed-out, or unavailable mandatory CI
  evidence as non-green. CI success remains evidence for human review and does
  not authorize merge, release, deployment, or model promotion.
- Fail during configuration initialization when upload, rate, outstanding, or
  retry-hint limits are non-positive or globally inconsistent.
- Keep generated datasets, feature banks, thresholds, evaluation runs, model
  weights, and runtime state outside Git.

## Deferred Capabilities

The v0.1 boundary does not promise multi-tenant isolation, a provisioned
distributed object-storage backend, automated image-retention scheduling,
lease heartbeats, an append-only attempt ledger, an external queue or workflow
engine, PLC integration, multi-camera lines, automated physical sorting, or
safety/regulatory certification.

## Related Sources

- [`../decisions/README.md`](../decisions/README.md)
- [`../decisions/0010-database-backed-prediction-reliability.md`](../decisions/0010-database-backed-prediction-reliability.md)
- [`../decisions/0011-database-backed-prediction-admission.md`](../decisions/0011-database-backed-prediction-admission.md)
- [`../engineering/data-lineage.md`](../engineering/data-lineage.md)
- [`../product/product-definition.md`](../product/product-definition.md)
- [`../../AGENTS.md`](../../AGENTS.md)
