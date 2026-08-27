# VDDAI Project Inspection Remediation Re-review R3

- Review ID: `VDDAI-REVIEW-PROJECT-2026-08-25-R3`
- Date: 2026-08-25
- Task: Final re-review of the approved current-head project inspection
  remediation
- Prior report: [`2026-08-25-project-inspection-r2.md`](2026-08-25-project-inspection-r2.md)
- Original report: [`2026-08-24-project-inspection.md`](2026-08-24-project-inspection.md)
- Scope: The complete approved remediation working-tree range on
  `fix/project-inspection-remediation`: decoded-image guardrails, duplicate
  registration race handling, pytest isolation, focused tests, configuration,
  and current contract documentation
- Base and current head: `0fdb8a4952d03fdcee7b5de942696e967b9a4fd4`
- Working-tree state before this report: 20 modified tracked files, five
  relevant untracked implementation/audit files, no staged files, and no
  remediation commits
- Explicit scope exclusion: concurrently appearing untracked `node_modules/`,
  `package.json`, and `package-lock.json` are unrelated user work. They were
  not created, modified, tested, or approved as part of this remediation and
  must not be staged with it.

## Contract sources and acceptance criteria reviewed

The final re-review used the repository-root, application, and ML `AGENTS.md`
files; `docs/README.md`; `docs/catalog.yaml`; current system requirements, data
lineage, and production-readiness documents; accepted ADRs 0009, 0010, and the
amended ADR 0011; both prior immutable reports; the exact implementation and
test range; and fresh default and PostgreSQL verification evidence.

The approved acceptance contract remains:

1. default and hard decoded-image ceiling of 16,777,216 pixels, with lower
   configuration permitted, equality accepted, and larger images rejected
   before storage and decode-heavy preprocessing;
2. safe `413` upload behavior with no retained object or prediction, safe
   terminal worker handling for legacy over-limit objects, and controlled
   Pillow warning/error translation;
3. transaction-safe duplicate registration with rollback, stable `409` for a
   confirmed duplicate only, and a PostgreSQL race yielding one success, one
   conflict, and one persisted user;
4. deterministic root pytest collection isolated from generated/runtime roots,
   with maintained default and marker suites retained; and
5. unchanged authentication, ownership, queue/worker lifecycle, preprocessing
   transform, ML splits, inference semantics, artifact schemas/checksums,
   lineage, registry selection, and human promotion gates.

Graphify was not used. Its prior local graph was stale, it is optional, and all
material conclusions were verified against direct sources and executable
checks.

## Verdict

`PASS`

All four preserved finding IDs are verified resolved. The hard pixel ceiling
now makes configuration validation, direct preprocessing construction,
Pillow's pinned warning threshold, executable behavior, and current
documentation one consistent fail-closed contract. The required PostgreSQL 16
concurrency suite passed against an isolated ephemeral database, including the
duplicate-registration race. The canonical gate passes in the populated
checkout that originally exposed pytest discovery failure.

No actionable finding remains in the approved remediation scope.

## Finding status summary

| Finding | Severity | Status |
|---|---|---|
| `VDDAI-REV-001` | HIGH | `VERIFIED RESOLVED` |
| `VDDAI-REV-002` | MEDIUM | `VERIFIED RESOLVED` |
| `VDDAI-REV-003` | MEDIUM | `VERIFIED RESOLVED` |
| `VDDAI-REV-004` | LOW | `VERIFIED RESOLVED` |

## Findings

### VDDAI-REV-001 — HIGH — Uploaded images have no decoded-pixel resource limit

- Status: `VERIFIED RESOLVED`
- Location: `app/core/config.py:6,19-24`,
  `app/services/image_dimension_policy.py:1-14`,
  `app/services/image_validation_service.py:38-113`, and
  `app/services/image_preprocessing_service.py:33-117`
- Fresh evidence: the 16,777,216-pixel ceiling is validated centrally; upload
  and shared preprocessing apply the strict-greater-than check before storage
  or decode-heavy transforms; and Pillow warning/error signals map to safe
  outcomes. Exact-boundary, plus-one, bomb-signal, API no-retention, and legacy
  worker terminal-failure tests pass in the canonical suite.
- VDDAI impact: authenticated inputs can no longer expand without the approved
  decoded-pixel bound, while accepted-image tensor and inference behavior are
  unchanged.
- Closure evidence: the canonical gate completed with 347 passed and seven
  optional skips; focused ceiling tests also passed independently.

### VDDAI-REV-002 — MEDIUM — Duplicate registration has a check-then-insert race

- Status: `VERIFIED RESOLVED`
- Location: `app/api/routes/auth.py:26-50`, `app/tests/test_auth.py:15-61`, and
  `app/tests/test_prediction_admission_postgres.py:90-135`
- Fresh evidence: commit-time `IntegrityError` handling rolls back before the
  post-conflict query, returns the existing `409` only when the submitted email
  exists, and re-raises unrelated integrity failures. The unit cases pass.
- PostgreSQL closure evidence: an ephemeral `postgres:16` container with no
  project volume was exposed only on `127.0.0.1:55432`. The four-test
  PostgreSQL integration file reported `4 passed in 5.81s`. Its barrier forced
  both duplicate-registration lookups to observe absence; assertions required
  sorted outcomes `[201, 409]` and exactly one matching user. The container was
  stopped, auto-removed, and the host port was verified closed afterward.
- VDDAI impact: the production database uniqueness constraint remains the
  concurrency authority without converting an expected duplicate race into an
  internal server error.

### VDDAI-REV-003 — MEDIUM — Canonical pytest discovery traverses generated state

- Status: `VERIFIED RESOLVED`
- Location: `pytest.ini:1-7` and `scripts/verify.ps1:180-184`
- Fresh evidence: default collection is constrained to `app/tests`, generated
  and runtime roots are excluded, and the repository-local basetemp setting is
  gone. The exact canonical gate again completed in the checkout containing
  the inaccessible generated artifact state.
- VDDAI impact: root verification no longer depends on ignored local dataset,
  artifact, upload, Graphify, virtual-environment, cache, or test-temporary
  contents.
- Closure evidence: `347 passed, 7 skipped` under the canonical gate. The one
  warning was a non-failing sandbox ownership issue for pytest's optional cache,
  not collection or test failure.

### VDDAI-REV-004 — LOW — Configured exact pixel boundary can be preempted by Pillow

- Status: `VERIFIED RESOLVED`
- Location: `app/core/config.py:6,19-24`,
  `app/services/image_preprocessing_service.py:33-57`,
  `app/tests/test_prediction_admission_service.py:201-234`,
  `app/tests/test_image_preprocessing_service.py:216-239`, and
  `docs/decisions/0011-database-backed-prediction-admission.md:33-47,85-102`
- Fresh evidence: `Settings` accepts only integers from 1 through the approved
  16,777,216 ceiling, and direct preprocessing construction applies the same
  bound. Tests accept the maximum, reject one above it, reject invalid direct
  constructor values, and assert that the approved ceiling does not cross
  pinned Pillow's warning threshold. Current application, ML, architecture,
  lineage, ADR, and operator documentation consistently state that
  configuration may lower but never raise the ceiling.
- VDDAI impact: operators now have one truthful exact-boundary contract, and no
  second lower Pillow threshold can preempt any supported configured value.
- Closure evidence: three focused ceiling tests passed; all 13 changed Python
  files passed Black; documentation validation and the canonical gate passed.

## Acceptance-criteria coverage

| Criterion | Implementation evidence | Verification evidence | Result |
|---|---|---|---|
| Hard/default 16,777,216 ceiling; lower configuration allowed | Pydantic `ge=1`/`le=MAX_IMAGE_PIXELS_HARD_LIMIT`; direct preprocessing bound | Maximum, one-above, invalid-value, and Pillow-threshold tests pass | Satisfied |
| Equality accepted and larger input rejected before heavy work | Shared strict `>` policy before storage/EXIF/RGB/resize/NumPy | Exact and plus-one service tests pass | Satisfied |
| Safe API rejection with no retained state | Validation precedes object write and prediction insertion | API test asserts `413`, zero rows, and zero files | Satisfied |
| Safe legacy object failure | Shared preprocessing raises terminally classified error | Worker test asserts one attempt and public `inference_failed` | Satisfied |
| Pillow warning/error control | Both boundaries promote warnings and catch warning/error classes | Synthetic warning and error fixtures pass | Satisfied |
| Duplicate race transaction behavior | Commit rollback/re-query and duplicate-only translation | Unit tests pass; PostgreSQL file passes 4/4 with `[201,409]` and one row | Satisfied |
| Deterministic pytest discovery | `testpaths`, `norecursedirs`, no repository basetemp | Canonical gate passes in populated checkout | Satisfied |
| Frozen ML and serving compatibility | Resource admission only; transform, schemas, artifacts, scorer, threshold, and package selection unchanged | Full preprocessing, ML, inference, package, and contract suite passes | Satisfied |
| Current documentation matches executable behavior | ADR and cataloged current docs state the same hard-ceiling rule | Documentation validation passes | Satisfied |

## Checks run

- Final reviewer run of `scripts/verify.ps1` with the process-local Git
  safe-directory setting — Python 3.14.3, pip 26.1.2, exact pins, `pip check`,
  documentation validation, and the full default suite passed:
  `347 passed, 7 skipped, 1 warning` in 85.78 seconds.
- `.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider`
  for the three focused hard-ceiling settings/preprocessing cases — `3 passed`
  in 3.96 seconds.
- `.venv\Scripts\python.exe -m black --check --workers 1 <13 changed Python files>`
  with an OS-temporary cache — all 13 files would be left unchanged.
- `git -c safe.directory=D:/Codes/visual-defect-ai-backend diff --check`, staged
  inventory, status, and in-scope diff statistics — no whitespace errors and no
  staged files; the approved tracked delta is 20 files with 504 insertions and
  77 deletions, plus the relevant untracked implementation/test/report files.
- Immediately preceding Coder closure check:
  `.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider app/tests/test_prediction_admission_postgres.py`
  with an inline URL to isolated PostgreSQL 16 — `4 passed in 5.81s`.
- Ephemeral database cleanup verification — the named test container no longer
  appeared in `docker ps -a`, and TCP port 55432 was closed.

## Checks not run

- The reviewer did not create a second PostgreSQL container solely to duplicate
  the immediately preceding successful isolated run. The exact command, test
  code, outcome, isolation mechanism, cleanup, and final repository state were
  inspected as current closure evidence.
- Docker Compose service wiring, the deployed production gate, the
  data-creating real-inference probe, and Alembic upgrade/downgrade were not
  run. The approved range changes no Compose definition, deployed service,
  migration, schema, registry selection, model package, or artifact.
- Repository-wide Black was not run because the root instructions document
  pre-existing baseline drift; every changed Python file was checked.
- No QA run, model registration, promotion, rollback, artifact generation,
  deployment, commit, push, merge, or persistent-data deletion was performed.

## Ordered remediation handoff

There are no open finding IDs and no further Coder remediation handoff.

The next workflow step is independent `$vddai-qa` against this exact working
tree and r3 report. After QA eligibility, synchronize any remaining durable
documentation through the documentation gate, then stop for human commit and
merge approval.

## Residual risks and assumptions

- The unrelated untracked Node package files are outside this review. They must
  be handled as a separate user-owned change and must not be accidentally
  included in this remediation.
- The seven default-suite skips remain optional PostgreSQL-dependent paths; the
  specific four-test admission/registration file has separate positive
  PostgreSQL 16 evidence.
- Pytest's optional cache cannot be updated by the sandbox account, but this no
  longer affects test discovery or execution.
- Existing artifacts remain compatible only when their sources fit the
  approved ceiling. No transform, schema, checksum, or lineage field changed,
  and no artifact regeneration is required for the MVTec AD `tile` pilot.
- The maintained W7 production risk register remains authoritative; this
  bounded remediation does not clear unrelated deployment, storage, retention,
  secret, rollback, probe-data, or monitoring risks.
- This pass does not authorize QA bypass, staging, commit, push, merge, model
  promotion, deployment, or release.
