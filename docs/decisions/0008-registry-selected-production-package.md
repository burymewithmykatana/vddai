# ADR 0008 — Registry-Selected Production Package

- Status: Accepted
- Date: 2026-08-13
- Amends: ADR 0004

## Context

ADR 0004 made production package selection explicit through two artifact-path
settings. That avoided unsafe directory scans, but promotion and rollback still
required configuration edits and a worker restart. W6D3 introduced an audited
registry with one production pointer and an explicit rollback target. W6D4 must
make serving follow that pointer without weakening package validation or the
frozen inference result contract.

## Decision

Production serving resolves exactly one model version from the `production`
environment record in the configured registry:

```text
MODEL_REGISTRY_PATH=artifacts/registry/model_registry.sqlite3
MODEL_ARTIFACT_ROOT=.
```

The resolver opens the registry read-only. It verifies the registry schema,
requires a non-empty production pointer and matching immutable candidate, and
resolves only that candidate's repository-relative manifest and feature-bank
locations beneath `MODEL_ARTIFACT_ROOT`. It rechecks the package-manifest
checksum before calling the existing fail-closed `ModelPackageLoader`.

The loader still validates the full artifact and cross-lineage contract from
ADR 0004. Its output must also match the registry's package, dataset, manifest,
and feature-bank identity. No serving component scans artifact directories,
queries the experiment ledger for a winner, or falls back to old path settings.

The worker resolves the production pointer before each queued inference job.
Heavy initialized packages and inference-service wrappers are cached by the
immutable promoted selection. A promotion therefore affects the next job
without a process restart, while an already loaded version is reused. Rollback
to the prior immutable selection safely reuses or reloads that exact version.

`GET /health/model` exposes only:

- selection status;
- immutable registry model version; and
- package ID used by the frozen inference contract.

The endpoint never exposes registry paths, artifact paths, checksums, metrics,
actors, reasons, or internal exception details. Unavailable or invalid registry
state returns a stable `503` diagnostic.

## Compatibility

`FEATURE_BANK_DIR` and `MODEL_PACKAGE_MANIFEST_PATH` remain accepted as legacy
environment keys so existing local `.env` files still parse, but serving
ignores them. Operators must create and explicitly promote a registry candidate
before production inference can succeed. A missing selection fails closed; it
does not revert to the legacy paths.

The persisted Week 5 `model_version` field continues to equal the package ID,
preserving the frozen inference contract. The registry version is the
deployment-selection identity and is available through safe diagnostics and
registry audit records.

## Human Approval Boundary

This resolution mechanism follows registry state; it does not authorize
changing that state. Real production promotion and rollback remain explicit
human-approved operations.

## Consequences

### Positive

- Serving, promotion, and rollback now share one auditable source of truth.
- The worker changes versions without hard-coded paths or a restart.
- Immutable-version caching preserves process reuse across requests.
- Missing, corrupt, incompatible, or lineage-mismatched selections fail closed.
- Operators can identify the selected version without exposing private paths.

### Negative

- The registry database becomes a required runtime dependency.
- A newly configured environment cannot run inference until a candidate is
  registered, staged, and explicitly promoted.
- Resolution adds one small read-only SQLite query before each queued job.

## Verification

Integration tests cover missing production state, safe diagnostics, serving a
selected package, following a promotion, following rollback without a restart,
and retaining safe terminal prediction failure when registry state is absent.
