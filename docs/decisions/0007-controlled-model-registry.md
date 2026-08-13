# ADR 0007 — Controlled Local Model Registry

- Status: Accepted
- Date: 2026-08-13

## Context

VDDAI needs to distinguish evaluated candidates from packages selected for
staging and production while preserving the Week 5 fail-closed inference
contract. Experiment completion is evidence, not deployment authorization.
Selecting the newest directory or mutating a package record in place would make
serving state ambiguous and rollback difficult to audit.

The v0.1.0 pilot is a single-workspace deployment, so a hosted registry service
would add infrastructure without improving the required control boundary.

## Decision

VDDAI will use a generated local SQLite registry. Its default artifact location
is `artifacts/registry/model_registry.sqlite3`, outside Git. The committed
contract and service define the registry schema and its fail-closed behavior.

Every candidate has an immutable model version derived from its package ID and
package-manifest SHA-256. Its record includes:

- source experiment run and full Git revision;
- repository-relative package-manifest and feature-bank locations;
- package-manifest and feature-bank checksums;
- dataset name, category, version, and manifest fingerprint;
- finite evaluation metrics; and
- registration actor and UTC timestamp.

Registration does not promote a package. Separate `staging` and `production`
environment records each select one exact version and retain one explicit
rollback target. A version that is not selected by either environment remains
a candidate. If a version is selected by both, production is its effective
stage.

Every promotion must provide an actor, reason, target environment, and
predeclared minimum metrics. Before changing state, the registry verifies:

1. all required validation metrics exist and meet their declared minimums;
2. the existing production package loader accepts the full artifact contract;
3. loaded package lineage matches the immutable candidate record; and
4. one smoke inference returns finite values with the frozen strict
   `score > threshold` decision semantics.

Production additionally requires that the exact version is already active in
staging. Rollback resolves only the explicit target recorded by the preceding
successful transition, re-runs the same gates, and swaps active and rollback
versions on success.

Promotion attempts are append-only audit records. Approved attempts record the
previous version, validated checks, actor, reason, and timestamps. Rejected
attempts retain public-safe rejection reasons and never change environment
state. Internal exception messages are not stored as registry evidence.

Official-test metrics may be retained as final evaluation evidence but are
rejected as promotion criteria. This prevents repeated production selection
from tuning the system against the frozen test set.

## Human Approval Boundary

The registry implements and tests mechanics; it does not grant deployment
authority. Promoting or rolling back the real production environment remains
an explicit human action under the repository approval policy. Tests use
temporary registries and do not modify the local operational registry.

## Consequences

### Positive

- Candidate registration, staging, production, and rollback are independently
  queryable and auditable.
- Serving can later resolve one explicit production pointer without scanning
  artifact directories.
- Schema, lineage, metric, and runtime checks fail closed before state changes.
- Rejected releases remain useful evidence without leaking internal errors.

### Negative

- SQLite remains local and requires an external backup process for evidence
  that must survive loss of the workspace.
- Promotion requires artifact availability at the registered locations.
- The v0.1.0 registry supports one active and one rollback version per
  environment rather than deployment percentages or multi-site rollout state.

## Verification

Registry tests cover immutable versions, checksum tampering, stage rules,
metric and package rejection evidence, successful staging and production
promotion, explicit rollback targets, and safe rollback.
