# ADR 0010 — Database-Backed Prediction Reliability

- Status: Accepted
- Date: 2026-08-21
- Migration revision: `20260820_03`

## Context

The PostgreSQL-backed worker originally committed `queued -> processing` before
inference and used `FOR UPDATE SKIP LOCKED` to prevent simultaneous claims. A
worker crash after that commit could leave a prediction permanently processing,
and result-persistence failures had no bounded retry state. The existing
locking guarantee prevented concurrent initial claims but did not define
recovery, replay, or attempt ownership after a lease expiry.

W7D2 must make duplicate execution, worker restart, and partial failure safe
without replacing the database queue, adding another infrastructure service,
or changing the frozen inference and public lifecycle contracts.

## Decision

### Creation and public lifecycle

Every accepted `POST /predictions` creates a distinct prediction record and
stored image object. Equal bytes, filenames, or repeated client requests are
not deduplicated, and v0.1.0 does not add an API idempotency key.

The public lifecycle vocabulary remains `queued`, `processing`, `completed`,
`failed`, and `needs_review`. Normal worker execution follows:

```text
queued -> processing -> completed | failed
```

Retry waiting is an internal substate of `processing`; it does not add a public
status. Clients see no partial result, attempt count, lease, retry timestamp, or
internal diagnostic. A terminal failure continues to expose only
`inference_failed`.

### Attempt ownership and transactions

The `predictions` table stores:

- `attempt_count`: the monotonically increasing attempt token;
- `lease_expires_at`: the active attempt's finite lease deadline; and
- `next_attempt_at`: the earliest time a waiting retry can be claimed.

The worker first recovers at most one expired active row, then selects the
oldest queued or due-retry row by `created_at` and `id`. Both recovery and claim
use a row lock with `SKIP LOCKED`. A claim increments `attempt_count`, assigns a
lease, clears retry metadata and stale result data, and commits before storage
or inference begins. No database transaction remains open during inference.

Settlement relocks and refreshes the prediction. Only `processing` with the
same attempt token, an active lease, and no retry timestamp may complete or
fail as that attempt. A stale worker result or failure is discarded. Completed,
failed, and `needs_review` rows are never reclaimed or overwritten.

The resulting guarantee is at-least-once computation and at-most-one current,
authoritative terminal persistence. This is execution idempotency for one
persisted prediction job; it is not request deduplication.

### Retry and failure policy

The process-level policy is deterministic and bounded:

| Setting | Default | Constraint |
|---|---:|---|
| `WORKER_MAX_ATTEMPTS` | `3` | Positive integer; includes the initial attempt |
| `WORKER_RETRY_DELAY_SECONDS` | `5.0` | Finite and greater than zero |
| `WORKER_ATTEMPT_LEASE_SECONDS` | `300.0` | Finite and greater than zero |

A due retry whose persisted count already meets a newly reduced maximum becomes
terminal without incrementing the count or invoking storage/inference.

| Failure boundary | Behavior |
|---|---|
| Generic image-storage backend read error | Retry, then terminal failure at exhaustion |
| Missing stored object or invalid object key | Terminal failure |
| Image preprocessing error | Terminal failure |
| Promoted-model resolution or model-package error | Terminal failure |
| Unknown post-claim execution or settlement validation error | Terminal failure where the current attempt can be settled |
| Result-commit database error | Roll back, relock, detect an already committed result, or schedule a bounded retry |
| Expired attempt lease | Discard that attempt's result and schedule a bounded retry or terminal exhaustion |
| Claim or recovery commit error | Roll back; leave durable state eligible for a later poll where possible |

Detailed exceptions remain internal. This table amends ADR 0009's earlier rule
that grouped every unreadable storage object into immediate terminal failure.

### Crash and restart behavior

| Interruption point | Durable outcome |
|---|---|
| Before claim commit | Row remains eligible; the transaction rolls back on connection/session close |
| After claim commit, before inference | Leased `processing`; recovered after expiry |
| During inference | Leased `processing`; recovered after expiry |
| After inference, before terminal commit | Leased `processing`; recovered after expiry and computation may repeat |
| Connection loss after terminal commit | Relock and accept only an already committed result from the same attempt |

Legacy `processing` rows created before this migration have neither lease nor
retry timestamp. The new worker treats them as stale and moves them into bounded
recovery. Old and new worker versions must not run concurrently because an old
worker does not enforce attempt fencing.

## Migration and Compatibility

Revision `20260820_03` is additive. It initializes existing rows with
`attempt_count=0` and null lease/retry timestamps without changing status,
results, lineage, timestamps, or internal diagnostics. The targeted downgrade
to `20260803_02` removes only these three columns and preserves prediction rows.

Operators must stop workers before upgrade or downgrade. Before downgrade they
must confirm that no processing row depends on lease or retry metadata; removal
of those columns cannot preserve ownership or eligibility for in-flight work.
The frozen inference result, preprocessing, package, lineage, authentication,
ownership, and public response contracts are unchanged.

## Consequences

- Concurrent workers still coordinate only through PostgreSQL.
- Worker restart no longer strands valid processing jobs indefinitely.
- Fixed leases may cause duplicate computation when valid inference exceeds the
  configured lease; attempt fencing prevents duplicate authoritative writes.
- The current row retains only current attempt/retry metadata, not an
  append-only attempt history.
- There is no lease heartbeat, Redis queue, Celery, Dramatiq, Kafka,
  distributed lock, or workflow engine in this decision.
- An API idempotency key remains out of scope for v0.1.0.

## Verification

Permanent tests cover lifecycle transitions, stale tokens, retry timing and
exhaustion, policy reduction, transient and terminal failures, claim and result
commit errors, ambiguous commits, restart recovery, stale-result fencing,
duplicate API submissions, migration preservation, and public diagnostic
disclosure. PostgreSQL integration verifies `SKIP LOCKED` concurrency and stale
worker fencing. Independent QA additionally exercised a real process exit after
claim commit, separate-process recovery and completion, and PostgreSQL upgrade,
downgrade, and re-upgrade with legacy data.

## Related Decisions

- [`0003-production-inference-contract.md`](0003-production-inference-contract.md)
- [`0005-inference-result-persistence.md`](0005-inference-result-persistence.md)
- [`0009-durable-image-storage-boundary.md`](0009-durable-image-storage-boundary.md)
