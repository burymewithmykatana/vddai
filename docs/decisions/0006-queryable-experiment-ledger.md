# ADR 0006 — Queryable Local Experiment Ledger

- Status: Accepted
- Date: 2026-08-12

## Context

The Week 4 MVTec AD tile baseline already produces versioned feature-bank,
score, threshold, evaluation, and run-manifest artifacts. Those files preserve
substantial lineage, but they do not provide one queryable record that ties an
attempt to its immutable ID, code revision, effective parameters, metrics,
artifact locations, checksums, timestamps, and terminal status.

Week 6 also needs experiment recording to remain distinct from candidate model
registration, promotion, and serving resolution. Adding a hosted tracker or a
new runtime service would expand the v0.1.0 operational surface without being
required for a single-machine pilot.

## Decision

VDDAI will use a generated, repository-local SQLite ledger for v0.1.0
experiment tracking. The default database is:

```text
artifacts/experiments/experiments.sqlite3
```

The database and all tracked ML artifacts remain outside Git. Committed source
code defines and validates the versioned tracker schema.

Each experiment run has an immutable run ID and records:

- experiment name and terminal status;
- dataset name, category, version, and manifest fingerprint;
- the full Git commit revision;
- effective parameters, including feature extractor, scorer `k`, threshold
  policy and quantile, threshold value, and random seed;
- queryable scalar evaluation metrics;
- repository-relative artifact locations, SHA-256 checksums, and artifact
  schema/code versions;
- UTC start/completion timestamps and a failure reason for failed attempts.

Parameters, metrics, and artifacts use normalized child tables so callers can
query them directly. Completed and failed records are terminal and cannot be
silently overwritten. Duplicate run IDs fail closed.

The Week 4 tracking command validates the frozen evaluation protocol and every
referenced checksum before recording the baseline. It imports the existing
official-test evaluation; it does not rerun, tune, or select against the test
set. The command refuses a dirty Git working tree so the recorded revision is
unambiguous.

## Boundaries

- Experiment tracking records what was attempted and observed.
- Candidate registration will validate and identify a complete package in a
  separate Week 6 step.
- Registration will not imply promotion.
- Production promotion and rollback remain explicit human-approved actions.
- Serving will continue to resolve only an explicitly selected package and
  will never scan experiment records for the newest run.

## Consequences

### Positive

- The baseline becomes queryable without a new service or dependency.
- Run, dataset, code, parameter, metric, and artifact lineage are joined in one
  durable local record.
- Generated binaries remain outside version control.
- Failed attempts remain audit evidence rather than appearing successful.
- The tracker can be replaced later behind an explicit migration boundary if
  hosted collaboration becomes necessary.

### Negative

- SQLite is local to one workspace and does not provide shared remote UI,
  multi-host coordination, or artifact transport.
- Operators must back up or export the generated database if they need durable
  evidence beyond the local workspace.
- The ledger references artifacts by repository-relative path; moving or
  deleting generated artifacts makes later retrieval unavailable, although
  their expected checksums remain recorded.

## Verification

- Tracker tests cover completed and failed terminal states, duplicate IDs,
  normalized queries, and terminal immutability.
- Baseline-import tests cover required lineage, parameters, metrics, artifacts,
  and checksum-tamper rejection.
- One complete local Week 4 baseline record is queried after the implementation
  is committed so its code revision is exact.
