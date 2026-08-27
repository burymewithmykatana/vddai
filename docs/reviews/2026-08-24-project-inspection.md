# VDDAI Current-HEAD Project Inspection

- Review ID: `VDDAI-REVIEW-PROJECT-2026-08-24-01`
- Date: 2026-08-24
- Task: Read-only inspection of the current project
- Scope: Current `master` release-readiness posture across API, authentication,
  storage, database queueing, worker recovery, ML/data lineage, model registry,
  package serving, migrations, tests, documentation, and deployment definition
- Branch: `master`
- Base and head: `0fdb8a4952d03fdcee7b5de942696e967b9a4fd4`
- Initial working-tree state: clean and synchronized with `origin/master`
- Review range limitation: no feature task, specification, acceptance criteria,
  or change range was supplied. This is a current-state inspection, not approval
  of a particular implementation task or authorization to release.

## Contract sources reviewed

The inspection used the repository-root, application, and ML `AGENTS.md` files;
`docs/README.md`; `docs/catalog.yaml`; the current system requirements, data
lineage, production-readiness, and agent-workflow documents; accepted ADRs
0001 through 0011 as applicable; current application, worker, migration, ML,
registry, package-loading, test, CI, Docker, and verification sources; and the
existing W7D3 and W7D4 review evidence.

Graphify was excluded from material evidence because
`python scripts/graphify_repository.py validate` reported that its recorded
head commit is stale. All conclusions below were verified against direct
repository sources and executable checks.

## Verdict

`CHANGES REQUIRED`

The central architecture is coherent and unusually well guarded for a pilot:
authenticated owner-scoped prediction access, database-backed admission and
queueing, `SKIP LOCKED` claims, leases and attempt fencing, immutable experiment
and model lineage, explicit human-controlled registry promotion, fail-closed
package validation, train/validation/test isolation, shared preprocessing, and
strict `score > threshold` behavior all have direct implementation and test
evidence. The intended application test suite passes when isolated from local
generated state.

Three actionable defects remain. The first permits a compact uploaded image to
declare a decoded size large enough to exhaust API or worker resources. The
second turns a concurrent duplicate registration into an internal server error.
The third makes the canonical repository verification depend on ignored local
directory contents and permissions; it failed in this inspection before test
collection completed.

## Findings

### VDDAI-REV-001 — HIGH — Uploaded images have no decoded-pixel resource limit

- Status: `OPEN`
- Location: `app/services/image_validation_service.py:37-88`,
  `app/services/image_preprocessing_service.py:62-77`, and
  `app/core/config.py:17`
- Evidence and failure scenario: upload storage limits encoded bytes to
  `MAX_IMAGE_SIZE_MB`, but validation accepts every positive width and height.
  A constructed PNG declaring `10000 x 10000` pixels was accepted as
  `ValidatedImage(... width=10000, height=10000)` while Pillow emitted only a
  `DecompressionBombWarning`. Pillow's installed warning threshold is
  89,478,485 pixels and its exception threshold is 178,956,970 pixels. The
  worker later applies EXIF transformation, RGB conversion, resize, and NumPy
  conversion, which can force large decoded allocations before the fixed-size
  model tensor exists. Highly compressible images can remain below the encoded
  byte limit while expanding to hundreds of megabytes.
- Why it matters to VDDAI: an authenticated client can exhaust memory or CPU,
  terminate a worker process, trigger repeated lease recovery, and reduce pilot
  availability. The existing W7-R02 ingress/spooling risk does not cover
  decoded pixel expansion after application admission.
- Required action: define a human-approved maximum decoded pixel/dimension
  policy, reject over-limit images before storage and again fail closed at the
  preprocessing boundary, convert Pillow decompression-bomb warnings/errors to
  a stable safe client/failure outcome, and document the effective limit. Do
  not weaken the deterministic preprocessing transform for accepted images.
- Verification required for closure: unit and API tests for exact-limit and
  limit-plus-one dimensions, a small encoded decompression-bomb fixture, no
  retained object or prediction on rejection, safe worker handling of a legacy
  stored over-limit object, the full application suite, and the canonical gate.

### VDDAI-REV-002 — MEDIUM — Duplicate registration has a check-then-insert race

- Status: `OPEN`
- Location: `app/api/routes/auth.py:18-40` and `app/models/user.py:14-19`
- Evidence and failure scenario: the route queries for an existing email and
  then commits a separate insert. The database unique constraint is the actual
  concurrency authority, but `db.commit()` has no `IntegrityError` handling or
  rollback. A direct route check with the initial query returning no row and
  commit raising a unique `IntegrityError` propagated that exception unchanged.
  Two simultaneous registrations can therefore both pass the query; the loser
  receives a generic `500` instead of the endpoint's established `409`.
- Why it matters to VDDAI: normal concurrent behavior violates the public auth
  response contract and produces avoidable internal-error telemetry at a
  security-sensitive boundary.
- Required action: treat the unique email constraint as authoritative, roll
  back the failed transaction, and translate only the duplicate-email conflict
  to the stable `409` response. Preserve other database failures as failures
  rather than masking every integrity error.
- Verification required for closure: route regression coverage for commit-time
  duplicate conflict and rollback, plus a PostgreSQL concurrency test showing
  exactly one `201`, one `409`, and one persisted user for simultaneous equal
  emails.

### VDDAI-REV-003 — MEDIUM — Canonical pytest discovery traverses generated state

- Status: `OPEN`
- Location: `pytest.ini:1-6` and `scripts/verify.ps1:180-184`
- Evidence and failure scenario: the canonical gate runs `python -m pytest -q`
  from the repository root, while `pytest.ini` defines a basetemp and markers
  but no `testpaths` or `norecursedirs`. Pytest therefore traverses ignored
  dataset, artifact, upload, and Graphify directories even though maintained
  tests live under `app/tests`. In this inspection the canonical gate passed
  dependency and documentation checks, then failed during collection with
  `PermissionError` on
  `artifacts/evaluations/baseline_q95_20260729`. The same local state also made
  the configured repository basetemp inaccessible to the sandbox account.
  Running `app/tests` with a fresh OS-temporary basetemp and per-process Git
  safe-directory setting completed with `334 passed, 6 skipped`.
- Why it matters to VDDAI: the declared one-command gate is not deterministic
  with respect to repository-ignored runtime state. It can fail, hang, or scan
  large local datasets/artifacts without any code or test change, weakening
  review and release evidence.
- Required action: constrain discovery to the maintained test root (or
  explicitly exclude every generated/runtime root) and make temporary test
  storage robust for supported local execution. Keep CI, the canonical script,
  marker gates, and direct pytest usage aligned.
- Verification required for closure: prove root-level `python -m pytest -q`
  and `scripts/verify.ps1` ignore populated generated roots, retain all 334
  default tests and intended optional PostgreSQL skips, and still collect the
  W6/W7 marker suites.

## Inspection coverage

| Boundary | Implementation evidence | Verification evidence | Result |
|---|---|---|---|
| Authentication and ownership | Bearer JWT subject resolution, inactive-user rejection, owner filters, explicit administrator read exception, non-disclosing cross-owner `404` | Passing API and contract tests; registration race separately recorded as VDDAI-REV-002 | Partially satisfied |
| Upload validation and storage | Encoded-byte limit, JPEG/PNG/WebP decode and media-type matching, opaque object keys, root confinement, orphan cleanup | Passing isolated application suite; constructed 100-megapixel PNG exposed VDDAI-REV-001 | Not satisfied |
| Admission and worker lifecycle | Per-user rate state, singleton-locked global admission, PostgreSQL `SKIP LOCKED`, bounded retry, leases, attempt fencing, rollback and terminal failure paths | Relevant default tests pass; optional PostgreSQL tests skipped in this environment | Satisfied by default evidence; integration evidence not refreshed |
| ML/data integrity | Deterministic train/validation split, train-only feature bank, validation-only threshold, official-test-only evaluation, shared preprocessing, fixed ResNet-18 and exact k-NN | Dataset, feature, scoring, threshold, evaluation, and contract tests pass | Satisfied |
| Registry and serving lineage | Immutable candidates, explicit environment state, human-gated promotion/rollback APIs, checksummed package members, exact selected version, no newest-artifact scan | Registry, promoted-resolution, package-loader, inference, and persistence tests pass | Satisfied |
| Database evolution | Four ordered Alembic revisions with one head | `python -m alembic heads` returned `20260821_04 (head)`; PostgreSQL upgrade/downgrade gate not rerun | Structurally satisfied; live integration not refreshed |
| Documentation and deployment definition | Cataloged current docs, risk register W7-R01 through W7-R08, pinned runtime, Compose API/worker/PostgreSQL/Redis topology | Documentation validator and Compose config passed | Satisfied with documented release blockers |
| Repository verification | Pinned dependency checks, docs validator, full pytest invocation, optional formatting and Compose checks | Canonical gate failed at pytest collection; isolated tests passed; see VDDAI-REV-003 | Not satisfied |

## Checks run

- `git -c safe.directory=D:/Codes/visual-defect-ai-backend status --short --branch`,
  log, head, merge-base, diff statistics, untracked inventory, and
  `git diff --check` — initial tree clean; `master` matched `origin/master` at
  `0fdb8a4`; no implementation delta or whitespace errors.
- `python scripts/graphify_repository.py validate` with a per-process Git
  safe-directory setting — unavailable because the graph head is stale; it was
  not used.
- `.\scripts\verify.ps1` — Python 3.14.3, pip 26.1.2, exact pins,
  `pip check`, and documentation validation passed; pytest collection then
  failed on an ignored artifact directory, so the canonical gate failed.
- `.venv\Scripts\python.exe -m pytest -q app/tests -p no:cacheprovider
  --basetemp <fresh OS temp>` with per-process Git safe-directory configuration
  — `334 passed, 6 skipped` in 64.44 seconds.
- `.venv\Scripts\python.exe -m black --check .` — failed on the documented
  pre-existing baseline: 35 files would be reformatted and 78 left unchanged.
- `.venv\Scripts\python.exe -m alembic heads` — one head,
  `20260821_04`.
- `docker compose -f docker-compose.yaml config --quiet` — passed; the sandbox
  emitted a warning that the host user's Docker config was unreadable.
- Direct crafted-image validation — a `10000 x 10000` PNG was accepted while
  Pillow emitted `DecompressionBombWarning`.
- Direct registration commit-failure exercise — an injected SQLAlchemy unique
  `IntegrityError` propagated from `register_user()`.

## Checks not run

- `scripts/run_production_gate.py` was not run because no explicitly disposable
  PostgreSQL 16 URL was supplied. Its contract correctly requires that external
  dependency and must not be made green by skips.
- Docker services and the data-creating real-inference probe were not started.
  No production package, registry selection, or disposable-stack authorization
  was supplied, and the probe intentionally retains test users, a prediction,
  and an image.
- Alembic upgrade, downgrade, and re-upgrade were not executed against a live
  PostgreSQL database.
- No model registration, promotion, rollback, artifact generation, deployment,
  merge, push, or persistent-data mutation was performed.

## Ordered remediation handoff

1. `VDDAI-REV-001`: approve and implement a decoded-image resource contract,
   safe rejection behavior, and adversarial regression coverage.
2. `VDDAI-REV-002`: make duplicate registration constraint-driven and
   transaction-safe, then verify PostgreSQL concurrency behavior.
3. `VDDAI-REV-003`: isolate pytest discovery and temporary state, then rerun the
   exact canonical gate in a populated developer checkout.
4. Re-review the bounded remediation range. If it passes, run independent QA,
   including disposable PostgreSQL and deployed real-inference evidence where
   authorized.

## Residual risks and assumptions

- The maintained W7-R01 through W7-R08 risk register remains authoritative:
  placeholder secrets, ingress body/spool limits, single-host local storage,
  retention, external model artifacts, rollback data loss, probe-created data,
  and missing unattended monitoring are not cleared by this inspection.
- The six isolated-suite skips are the repository's optional PostgreSQL paths;
  they are not positive production-gate evidence.
- Repository-wide Black drift is acknowledged by the current agent contract
  and was not converted into an unrelated remediation request.
- Passing default tests supports current behavior but does not substitute for
  a task-specific acceptance contract, independent QA, human model-promotion
  approval, human merge approval, or deployment approval.
