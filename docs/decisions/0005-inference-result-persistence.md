# ADR 0005 — Auditable Inference Result Persistence

- Status: Accepted
- Date: 2026-08-03
- Migration revision: `20260803_02`

## Context

The production worker needs to persist each completed image-level decision as
one queryable, immutable audit snapshot. Frequently displayed or filtered
values belong in typed columns, while the complete versioned model-package
lineage contains many related fields that must remain together.

## Decision

The `predictions` table uses explicit nullable columns for lifecycle status,
label, anomaly score, threshold, package ID (`model_version`), latency in
milliseconds, and created/processing-started/completed timestamps. Queued rows
leave result columns null. The worker changes a queued row to processing in one
transaction, then writes every successful result field and `completed` status
in one later transaction. Failed transitions clear every result field before
writing the terminal state and internal diagnostic.

`model_lineage` is a JSON snapshot validated against
`vddai.inference_package.v1`. It includes the contract and package schema,
package ID, preprocessing schema, MVTec AD dataset/category/version and
manifest fingerprint, ResNet-18 identity/weights/layer/dimension, feature-bank
checksum and metadata, Euclidean mean-k-nearest scorer configuration, and the
normal-validation threshold policy and checksum. Package-relative artifact
names are audit metadata; local absolute paths, secrets, Python objects,
weights, and feature-bank content are excluded.

The obsolete `confidence` column and public key remain compatibility-only and
always null. Anomaly distance is stored only as `anomaly_score` and is never
presented as a probability.

All persisted timestamps use the repository's timezone-naive UTC convention.
The authenticated read API returns safe image metadata and an opaque record ID,
not the internal `image_path`.

## Migration

Apply all migrations before starting API or worker processes:

```powershell
alembic upgrade head
```

Revision `20260803_02` adds only nullable `processing_started_at`, so existing
rows and result data are preserved. It intentionally does not fabricate a
start time for legacy rows. Its reversible downgrade is:

```powershell
alembic downgrade 20260801_01
```

The migration test exercises upgrade, data preservation, the targeted
downgrade, and the complete Week 5 downgrade chain. Operators should audit any
legacy terminal rows with a null processing timestamp before exposing them
through the stricter v1 read schema.

## Consequences

- Completed rows are reproducible from the exact persisted decision inputs and
  package lineage without storing large artifacts in the database.
- Domain lifecycle methods and the read schema reject partial completed rows;
  the database remains nullable so queued rows and valuable legacy data survive
  migration without a destructive rewrite.
- Local image storage and database-backed polling remain deployment and
  reliability constraints. Multi-instance object storage, leases/retries, and
  broader recovery belong to later reliability work.
