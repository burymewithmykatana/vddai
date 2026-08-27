# VDDAI Application Instructions

These instructions extend the repository-root `AGENTS.md` for every change
under `app/`. The root mission, ML invariants, Git rules, verification gate,
and human approval boundaries still apply.

## Application Boundary

`app/` owns the online product path:

```text
authenticated upload
  -> validated backend-independent image storage
  -> queued database row
  -> worker claim
  -> frozen-package inference
  -> atomic terminal persistence
  -> owner-scoped API readback
```

Keep HTTP concerns, persistence behavior, inference contracts, and worker
orchestration in their existing layers. Do not bypass a layer merely to make a
test or one endpoint simpler.

## Module Ownership

- `api/routes/`: HTTP status codes, request dependencies, routing, and response
  models. Routes coordinate work; they must not reimplement security,
  preprocessing, scoring, or package validation.
- `api/deps.py`: database-session lifetime and current-user authentication.
- `contracts/`: frozen, cross-component inference vocabulary and semantics.
  Services, models, schemas, and workers must import these definitions instead
  of duplicating them.
- `core/`: settings, logging, password handling, and token behavior.
- `db/`: SQLAlchemy base, engine/session construction, and initialization.
- `models/`: persistence mappings and prediction lifecycle transitions.
- `schemas/`: public request/response validation and serialization.
- `services/`: image validation/storage/preprocessing, model-package loading,
  and inference operations.
- `workers/`: database queue claiming, transaction handling, and terminal job
  orchestration.
- `tests/`: application, integration, migration, and inference-contract
  regression coverage.

`app/main.py` owns application startup and router registration. A route module
is not live merely because the file exists; router exposure must be explicit
and tested.

## Dependency Direction

Prefer this dependency flow:

```text
routes -> dependencies/services/models/schemas
workers -> services/models/contracts
services -> contracts/core and offline ML primitives
schemas/models -> contracts
```

Avoid importing routes from services, HTTP exceptions into domain models, or
worker orchestration into inference services. Do not introduce a second copy
of prediction labels, failure codes, score semantics, lineage models, or
package-selection rules.

## Authentication and Authorization

- Authentication uses a Bearer JWT whose `sub` resolves to an integer user ID.
- Missing, malformed, invalid, expired, or unknown-user credentials return the
  existing non-specific `401` behavior.
- Inactive authenticated users return `403`.
- Prediction creation derives ownership from the authenticated user. Never
  accept a client-selected owner ID or trusted filesystem path.
- Prediction reads and history remain owner-scoped. Preserve the existing
  administrator exception deliberately and test it.
- Unauthorized access to another user's individual prediction returns the
  same non-disclosing `404` used for a missing prediction.
- Never serialize password hashes, secrets, raw tokens, internal image paths,
  stack traces, or internal exception messages.

Any change to token claims, credential responses, active-user behavior,
ownership, or administrator access is a security-policy change and requires
the human approval defined in the root instructions.

## Upload and Storage Boundary

Uploaded files must remain encoded-size-limited, decoded-pixel-limited,
non-empty, content-decoded, restricted to the supported JPEG/PNG/WebP formats,
consistent with their declared media type, and positive in width and height.
The default and human-approved hard ceiling for the decoded-image budget is
16,777,216 pixels; configuration may lower but never raise it. Over-limit
uploads return the stable `413` before storage; legacy stored objects fail
closed before decode-heavy preprocessing.

Storage object keys are server-generated. API clients must not choose keys or
destination paths. Public responses expose safe image metadata, not the opaque
key or its backend-specific location.

The current create flow stores the validated image before inserting the queued
prediction. If database persistence fails, preserve all three behaviors:

1. roll back the database transaction;
2. attempt to delete the newly stored orphan;
3. log cleanup failure internally without replacing the original failure.

Do not broaden deletion to client-supplied or unvalidated keys. The API and
worker use the image-storage service contract; only its local implementation
may resolve keys to filesystem paths. Provisioning a distributed object-store
backend and record-coupled deletion remain deferred implementation work.

## Database and Transaction Rules

`get_db()` owns session creation and closing; it does not implicitly commit.
The route or worker that owns a unit of work must make its commit/rollback
boundary explicit.

Use model lifecycle methods for prediction transitions rather than assigning a
collection of result and timestamp fields ad hoc. Keep SQLAlchemy models,
Pydantic schemas, migrations, and lifecycle tests synchronized.

Application startup currently calls `Base.metadata.create_all()`, but this is
not a substitute for Alembic. Every persistent schema evolution still requires
a migration under `alembic/` as specified by the root instructions.

Tests set `ENVIRONMENT=test` and the SQLite test database in
`app/tests/conftest.py` before importing application modules. Settings and the
SQLAlchemy engine are initialized at import time, so do not reorder test imports
in a way that initializes them against Docker-only or non-test configuration.

## Prediction Lifecycle

Preserve the state vocabulary:

- `queued`
- `processing`
- `completed`
- `failed`
- `needs_review`

Preserve these state invariants:

- `queued`: creation timestamp only; no processing/terminal timestamp, result,
  or failure code.
- `processing`: creation and processing-start timestamps; no terminal
  timestamp, result, or failure code.
- `completed` and `needs_review`: complete validated inference result and all
  lifecycle timestamps; no failure code.
- `failed`: processing and terminal timestamps plus the stable public
  `inference_failed` code; no stale result fields.

Timestamps remain timezone-naive UTC and must be monotonic across the lifecycle.
The deprecated `confidence` field remains `null`. The anomaly distance is
exposed only through `anomaly_score` and must not be described as probability
or confidence.

The persisted label must agree with `classify_anomaly_score()`, `model_version`
must equal the lineage package ID, and the persisted threshold must equal the
lineage threshold. Reject partial or contradictory terminal results.

## Worker and Queue Rules

The queue is PostgreSQL-backed. Redis is not the current prediction broker.

Preserve the worker sequence:

1. recover at most one expired or legacy lease-less processing row;
2. select the oldest queued or due-retry row by creation time and ID;
3. claim it with `FOR UPDATE SKIP LOCKED`, increment its attempt token, assign a
   lease, and commit the claim;
4. retrieve its stored input through the image-storage service by opaque key;
5. relock and persist the full completed result only for the current attempt; or
6. roll back, relock, and schedule a bounded retry or safe terminal failure.

Do not hold the claim transaction open during inference, weaken concurrent
claim protection, or permit a stale attempt to settle. Detailed failures belong
in internal logs/database diagnostics; API clients receive only the stable
public failure code.

Prediction admission counts both `queued` and `processing`, including retry
waiting and expired work, while excluding terminal statuses. Preserve the
database-backed per-user rate state and singleton-row-locked count-and-insert
transaction; do not replace it with a race-prone count followed by an unlocked
insert. ADR 0010 defines attempt reliability and ADR 0011 defines admission.

## Production Inference Integration

`app/contracts/inference.py` owns the online input, score, threshold, label,
lineage, and result contracts. Import it rather than redefining serving rules.

`ModelPackageLoader` must validate the entire selected package before returning
any runtime object. `AnomalyInferenceService` must score with an already-loaded,
immutable package. Requests and individual predictions must never rebuild,
retune, download, or silently substitute package members.

The package loader and inference service use one-entry process caches. Cache
reset helpers are test-only and must remain guarded by `ENVIRONMENT=test`.
Week 6 active-package resolution may change how the explicit promoted package
is located, but it must preserve fail-closed validation, deterministic package
identity, process-level reuse, and auditable promotion state.

Inference latency starts immediately before stored-image preprocessing and
ends after the final label decision. It excludes queue wait, package
initialization, and database commits. Preserve this measurement boundary unless
the versioned contract is intentionally changed.

## Focused Verification

Run the smallest relevant test group while developing. Useful existing commands
include:

```powershell
python -m pytest -q app/tests/test_prediction_api.py
python -m pytest -q app/tests/test_inference_contract.py
python -m pytest -q app/tests/test_model_package_loader.py
python -m pytest -q app/tests/test_anomaly_inference_service.py
python -m pytest -q app/tests/test_image_preprocessing_service.py
python -m pytest -q app/tests/test_week05_migration.py
```

Changes spanning several boundaries should run the related groups together.
Before completion, run the applicable repository-wide verification from the
root `AGENTS.md`; focused tests do not replace the full gate.

## Code Review Rules

Treat these as high-priority findings in `app/` changes:

- authentication or ownership can be bypassed;
- public responses expose internal paths, diagnostics, secrets, or hashes;
- upload persistence can leave an avoidable object orphan after transaction
  failure;
- lifecycle transitions permit partial, stale, or contradictory results;
- worker transaction changes allow duplicate claims or invalid intermediate
  states;
- inference code bypasses the frozen contract or adds a permissive fallback;
- package selection becomes implicit, non-auditable, or newest-by-directory;
- tests pass only by weakening production behavior or test-environment guards;
- a schema change lacks a matching Alembic migration and compatibility test.

For each finding, identify the violated boundary and the safe existing pattern
to follow. Keep formatting-only observations separate from correctness and
contract risks.
