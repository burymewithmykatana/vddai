# VDDAI System Requirements

- Status: Current
- Last reviewed: 2026-08-10
- Scope: v0.1 visual-inspection feasibility-pilot platform

## Product Boundary

VDDAI must support one constrained inspection project and one explicitly
configured model package at a time. It must not claim universal defect
detection, safety-certified automated rejection, or customer validation from
public benchmark results.

## Functional Requirements

- Authenticate users with bearer JWTs and reject inactive users.
- Accept size-limited JPEG, PNG, and WebP uploads after structural decoding and
  media-type validation.
- Generate server-controlled storage paths and owner-scoped prediction records.
- Process predictions asynchronously through the database-backed worker queue.
- Return prediction lifecycle state and safe completed-result fields.
- Preserve prediction history and the exact model-package lineage used for each
  successful result.

## Security and Privacy Requirements

- Derive ownership from the authenticated identity, never from request input.
- Prevent ordinary users from accessing another user's predictions.
- Keep internal paths, secrets, password hashes, stack traces, and private model
  artifacts out of public responses.
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
- Prevent concurrent workers from claiming the same queued row.
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
- Validate dependencies, documentation structure, tests, and Compose wiring
  through the repository verification gate.
- Keep generated datasets, feature banks, thresholds, evaluation runs, model
  weights, and runtime state outside Git.

## Deferred Capabilities

The v0.1 boundary does not promise multi-tenant isolation, distributed object
storage, worker leases and retry orchestration, PLC integration, multi-camera
lines, automated physical sorting, or safety/regulatory certification.

## Related Sources

- [`../decisions/README.md`](../decisions/README.md)
- [`../engineering/data-lineage.md`](../engineering/data-lineage.md)
- [`../product/product-definition.md`](../product/product-definition.md)
- [`../../AGENTS.md`](../../AGENTS.md)
