# ADR 0011 — Database-Backed Prediction Admission

- Status: Accepted
- Date: 2026-08-21
- Migration revision: `20260821_04`

## Context

Authenticated prediction creation previously admitted every valid upload and
checked the configured file-size limit only after reading the complete
`UploadFile` into application memory. Simultaneous requests had no per-user or
global capacity boundary, so a burst could grow the PostgreSQL-backed queue and
local image storage without a deterministic limit.

W7D3 must add resource guardrails without changing the W7D2 worker state
machine, moving queue authority to Redis, adding distributed coordination, or
changing the successful prediction response.

## Decision

### Upload memory boundary

`ImageStorageService` rejects a reported oversize before reading when the
framework supplies a size, then authoritatively reads at most the configured
maximum plus one byte. Exactly the configured maximum is accepted; a larger
upload returns `413` before image decoding or object storage. The file is still
closed on every path.

This bounds application-memory consumption after FastAPI supplies the
`UploadFile`. It does not replace deployment-level request-body or temporary
spool limits because multipart receipt occurs before route execution.

### Request-frequency state

Each authenticated user has one fixed-window row in
`prediction_request_rate_windows`. Prediction creation locks the corresponding
`users` row, initializes or updates the current window, and commits the consumed
request slot before reading or storing the upload. Consequently, authenticated
requests that later fail validation, storage, or queue admission still consume
a rate slot. A request rejected because the window is already exhausted does
not extend it.

Administrators are keyed by their own user ID and receive no creation-limit
exemption. Their existing cross-owner read privilege is unchanged.

### Atomic outstanding admission

The `prediction_admission_control` table contains exactly the singleton row
`id=1`. After successful storage, every API process locks this row with
`SELECT ... FOR UPDATE`, checks per-user and global outstanding counts, inserts
the queued `Prediction`, and commits before releasing the lock.

Only `queued` and `processing` count as outstanding. This includes active
attempts, retry-waiting work, and expired or legacy processing rows pending ADR
0010 recovery. `completed`, `failed`, and `needs_review` do not count.

Uploads and storage writes occur before the singleton lock, so filesystem and
image-validation work never holds the global database admission lock. Worker
transitions do not acquire the lock because they can only reduce outstanding
pressure. A concurrent terminal transition may cause a conservative rejection
but cannot cause admission overshoot.

### Defaults and public failures

| Setting | Default | Constraint |
|---|---:|---|
| `MAX_IMAGE_SIZE_MB` | `5` | Positive integer |
| `PREDICTION_RATE_LIMIT_REQUESTS` | `10` | Positive integer |
| `PREDICTION_RATE_LIMIT_WINDOW_SECONDS` | `60` | Positive integer |
| `PREDICTION_USER_OUTSTANDING_LIMIT` | `5` | Positive integer |
| `PREDICTION_GLOBAL_OUTSTANDING_LIMIT` | `50` | Positive and not below the per-user limit |
| `PREDICTION_CAPACITY_RETRY_AFTER_SECONDS` | `5` | Positive integer |

Request-frequency and per-user outstanding exhaustion return `429`. Global
capacity exhaustion returns `503`. Retryable failures include an integer
`Retry-After`: the exact remaining fixed-window duration for request frequency
and the configured capacity hint for outstanding limits. Oversize returns
`413` without a retry hint because the same body cannot succeed.

Public errors never expose occupancy counts, other users, internal paths,
database details, or exceptions. If admission rejects after storage, the route
rolls back and performs the existing best-effort orphan cleanup without hiding
the original failure.

## Migration and Compatibility

Revision `20260821_04` creates the two internal admission tables and seeds the
singleton row when the existing users and predictions schema is present. Fresh
databases created through application metadata also seed the singleton during
initialization. Existing users, predictions, results, images, retry metadata,
and lineage are not rewritten.

The targeted downgrade to `20260820_03` removes only the W7D3 tables. It loses
ephemeral fixed-window counters but preserves prediction history and the W7D2
queue lifecycle. The successful `POST /predictions` response and every public
prediction status remain unchanged.

## Consequences

- PostgreSQL remains the source of truth for queue and admission behavior.
- Concurrent API instances cannot overshoot configured outstanding limits.
- One short singleton-row transaction serializes accepted job inserts, which is
  an intentional v0.1 correctness-over-throughput tradeoff.
- Rate state is bounded to one row per user and is deleted with that user.
- Stale processing work continues to consume capacity until ADR 0010 recovery.
- Redis queueing, distributed locks, request deduplication, public idempotency
  keys, workflow engines, and deployment-level body limits remain out of scope.

## Verification

Permanent tests cover exact upload-size boundaries, bounded reads, rate-window
reset and retry hints, per-user and global capacity, status counting,
administrator behavior, object cleanup, configuration validation, migration
preservation, and PostgreSQL simultaneous request/admission serialization.

## Related Decisions

- [`0009-durable-image-storage-boundary.md`](0009-durable-image-storage-boundary.md)
- [`0010-database-backed-prediction-reliability.md`](0010-database-backed-prediction-reliability.md)
