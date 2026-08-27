# VDDAI Project Inspection Remediation Re-review

- Review ID: `VDDAI-REVIEW-PROJECT-2026-08-25-R2`
- Date: 2026-08-25
- Task: Re-review the approved remediation of the current-head project
  inspection findings
- Prior report: [`2026-08-24-project-inspection.md`](2026-08-24-project-inspection.md)
- Scope: Complete tracked and untracked working-tree remediation on
  `fix/project-inspection-remediation`, including runtime code, tests,
  configuration, current documentation, amended ADR 0011, and the prior
  immutable review report
- Base and current head: `0fdb8a4952d03fdcee7b5de942696e967b9a4fd4`
- Working-tree state: 20 modified tracked files and four relevant untracked
  files before this re-review report; no staged changes or remediation commits
- Review-range limitation: the implementation is an uncommitted working-tree
  delta. No disposable PostgreSQL URL was configured, so the required real
  database registration-race test could be collected but not executed.

## Contract sources and acceptance criteria reviewed

The re-review used the repository-root, application, and ML `AGENTS.md` files;
`docs/README.md`; `docs/catalog.yaml`; the current system requirements, data
lineage, and production-readiness contracts; accepted ADRs 0009, 0010, and the
2026-08-25 amendment to ADR 0011; the exact implementation and test diff; and
the prior immutable inspection report.

The human-approved remediation contract was:

1. enforce a 16,777,216 decoded-pixel default at upload and shared
   preprocessing boundaries, accepting equality and rejecting larger images
   safely without retained upload or prediction state;
2. convert Pillow decompression-bomb warnings and errors into controlled API
   or worker outcomes while preserving the frozen preprocessing transform and
   artifact compatibility for accepted MVTec AD `tile` inputs;
3. roll back commit-time registration integrity failures and translate only a
   confirmed duplicate email to the established `409` response, including a
   real PostgreSQL two-request race check;
4. isolate default pytest collection and temporary state from generated and
   ignored repository roots while retaining the default and W6/W7 suites; and
5. preserve authentication, ownership, database queue and worker lifecycle,
   inference semantics, model/package lineage, schema, artifacts, and human
   promotion gates.

Graphify was not used. The prior inspection established that its local graph
was stale, and this bounded re-review verified all material conclusions against
the exact diff and direct repository sources.

## Verdict

`CHANGES REQUIRED`

The approved default decoded-image boundary, safe upload/worker outcomes,
registration rollback behavior, pytest isolation, frozen preprocessing
transform, and documentation updates are implemented coherently. The canonical
gate passes in the same checkout that previously failed on generated artifact
state.

The review cannot close `VDDAI-REV-002` because its explicitly required live
PostgreSQL concurrency check was skipped. One new low-severity contract defect
was also found: configuration accepts pixel budgets above Pillow's warning
threshold while the implementation rejects an image exactly at such a
configured budget, contradicting the documented equality rule. This behavior
is fail-closed and does not affect the approved 16,777,216 default, but the
operator-visible configuration contract must be made internally consistent.

## Finding status summary

| Finding | Severity | Status |
|---|---|---|
| `VDDAI-REV-001` | HIGH | `VERIFIED RESOLVED` |
| `VDDAI-REV-002` | MEDIUM | `STILL OPEN` |
| `VDDAI-REV-003` | MEDIUM | `VERIFIED RESOLVED` |
| `VDDAI-REV-004` | LOW | `OPEN` |

## Findings

### VDDAI-REV-001 — HIGH — Uploaded images have no decoded-pixel resource limit

- Status: `VERIFIED RESOLVED`
- Location: `app/core/config.py:17-19`,
  `app/services/image_dimension_policy.py:1-14`,
  `app/services/image_validation_service.py:38-113`, and
  `app/services/image_preprocessing_service.py:33-113`
- Fresh evidence: `MAX_IMAGE_PIXELS` defaults to 16,777,216; the shared helper
  rejects only `width * height > maximum_pixels`; upload validation executes
  the policy before verification and object storage; shared preprocessing
  executes it before EXIF transformation, RGB conversion, resize, and NumPy
  allocation. Pillow warning and error classes are translated to safe `413` or
  `ImagePreprocessingError` outcomes. API regression coverage proves that an
  over-limit upload leaves zero prediction rows and no stored files, and worker
  coverage proves that a legacy over-limit object reaches the stable terminal
  `inference_failed` state without retry.
- Why it matters to VDDAI: the authenticated input path now has an explicit,
  fail-closed decoded-allocation boundary without changing accepted-image
  tensor semantics, model normalization, scoring, threshold equality, or
  lineage.
- Closure verification: the exact-boundary, plus-one, warning/error, API
  retention, and worker tests all passed in the full canonical run. ADR 0011,
  current architecture/engineering documentation, `.env.example`, and the
  repository README describe the approved default and compatibility effect.
- Follow-up: see new `VDDAI-REV-004` for a non-default configuration-range
  inconsistency; it does not reopen the approved-default resource fix.

### VDDAI-REV-002 — MEDIUM — Duplicate registration has a check-then-insert race

- Status: `STILL OPEN`
- Location: `app/api/routes/auth.py:26-50`, `app/tests/test_auth.py:15-61`, and
  `app/tests/test_prediction_admission_postgres.py:90-135`
- Fresh evidence: the route catches `IntegrityError`, rolls back before any
  further session use, re-queries the submitted email, returns the established
  `409` only when that email now exists, and re-raises an unrelated integrity
  failure. Unit regression tests for rollback, duplicate translation, and
  unrelated-error preservation passed in the canonical run. The PostgreSQL
  test uses separate sessions and a barrier to force both initial lookups to
  observe absence, then requires sorted outcomes `[201, 409]` and exactly one
  persisted user.
- Remaining failure scenario: the concurrency test was skipped because
  `VDDAI_TEST_POSTGRES_DATABASE_URL` is not configured. Static review supports
  the transaction design, but the original finding explicitly required live
  PostgreSQL evidence for unique-constraint blocking, rollback, visibility,
  and final row count. That evidence cannot be inferred from SQLite/unit tests.
- Why it matters to VDDAI: PostgreSQL is the production persistence authority,
  and this finding concerns behavior created specifically by simultaneous
  transactions.
- Required action: run
  `.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider app/tests/test_prediction_admission_postgres.py`
  with `VDDAI_TEST_POSTGRES_DATABASE_URL` pointing to an explicitly disposable
  PostgreSQL 16 database. No code change is requested unless the test fails.
- Verification required for closure: the test file must report all four tests
  passed, including one `201`, one `409`, and one persisted user for the equal
  email race. Preserve the database URL and run context as QA/re-review
  evidence without exposing credentials.

### VDDAI-REV-003 — MEDIUM — Canonical pytest discovery traverses generated state

- Status: `VERIFIED RESOLVED`
- Location: `pytest.ini:1-7` and `scripts/verify.ps1:180-184`
- Fresh evidence: `testpaths = app/tests` confines default collection to the
  maintained test root; generated/runtime roots are also listed in
  `norecursedirs`; and the repository-local `--basetemp=.pytest_tmp` setting was
  removed. The previously inaccessible generated artifact directory remained
  present while the exact canonical gate completed successfully.
- Why it matters to VDDAI: the one-command verification gate no longer depends
  on ignored dataset, artifact, upload, Graphify, virtual-environment, cache, or
  old test-temporary contents.
- Closure verification: `scripts/verify.ps1` completed with 346 passed and
  seven optional skips. Independent collection retained 10 W6 tests and 170 W7
  tests out of 353 total collected items.

### VDDAI-REV-004 — LOW — Configured exact pixel boundary can be preempted by Pillow

- Status: `OPEN`
- Location: `app/core/config.py:17-19`,
  `app/services/image_validation_service.py:45-47,90-101`,
  `app/services/image_preprocessing_service.py:78-109`, and
  `docs/decisions/0011-database-backed-prediction-admission.md:33-47,85-101`
- Evidence and failure scenario: `MAX_IMAGE_PIXELS` accepts every positive
  integer, and ADR 0011 states that exactly the configured budget is accepted.
  Both image services first convert Pillow's `DecompressionBombWarning` to an
  exception. With `MAX_IMAGE_PIXELS=100000000`, a synthetic `10000 x 10000`
  image is exactly at the configured budget but upload validation returns `413`
  and preprocessing raises `ImagePreprocessingError`, because pinned Pillow's
  lower warning threshold fires during `Image.open()` before the shared policy
  check. The re-review reproduced both outcomes directly.
- Why it matters to VDDAI: the default is safe, but operators cannot derive the
  actual accepted boundary from the validated setting and accepted ADR. This
  is contract drift at a security/resource configuration boundary and leaves
  untested behavior for larger configured values.
- Required action: make the accepted configuration range and runtime equality
  rule consistent while preserving fail-closed Pillow warning/error handling.
  The bounded option is to reject configuration values above the largest
  human-approved cap for which the documented exact-boundary rule is true; any
  decision to define a different effective limit is a security-policy contract
  change and requires human approval. Align current documentation with the
  resulting single rule.
- Verification required for closure: add settings tests for the maximum
  supported value and one-above configuration, plus service tests proving
  equality and over-limit behavior cannot be preempted by a second undocumented
  threshold. Rerun changed-file formatting, documentation validation, and the
  canonical gate.

## Acceptance-criteria coverage

| Criterion | Implementation evidence | Verification evidence | Result |
|---|---|---|---|
| Approved 16,777,216 default; equality normal and plus-one rejected | Positive setting, shared strict-greater-than dimension policy, upload and preprocessing enforcement | Canonical exact/plus-one tests pass | Satisfied for approved default |
| Safe Pillow warning/error handling | Both services promote warning to exception and catch warning/error explicitly | Warning and error fixtures pass in storage tests; preprocessing warning path passes | Satisfied |
| No retained object or prediction after upload rejection | Validation precedes object write; API route receives `413` before admission | API regression asserts zero rows and zero files | Satisfied |
| Safe legacy stored-object handling | Shared preprocessing raises `ImagePreprocessingError`; existing worker policy treats it as terminal | Worker regression passes with one attempt and `inference_failed` | Satisfied |
| Preserve frozen preprocessing and ML lineage | Only a pre-transform resource check was added; transform, schemas, model package, scorer, threshold, and artifacts are unchanged | Existing preprocessing, ML, inference, package, and contract tests pass in the full suite | Satisfied |
| Duplicate race returns one success and one conflict | Commit-time rollback/re-query logic and real PostgreSQL barrier test are present | Unit behavior passes; PostgreSQL test skipped | Not yet verified |
| Root pytest ignores generated state and retains marker suites | `testpaths`, `norecursedirs`, and removal of repository basetemp | Canonical gate passes; W6/W7 collect 10/170 tests | Satisfied |
| Configuration and documentation agree | Default and common behavior agree | Direct high-cap probe contradicts exact configured-boundary text | Not satisfied; `VDDAI-REV-004` |

## Checks run

- `git -c safe.directory=D:/Codes/visual-defect-ai-backend status --short`,
  diff statistics, untracked inventory, and `git diff --check` — complete
  working-tree range inspected; no staged files, generated binaries, secrets,
  or whitespace errors. Git emitted only the existing LF-to-CRLF notice for
  `.env.example` and sandbox access warnings for the host global ignore file.
- `scripts/verify.ps1` with the process-local Git safe-directory setting —
  Python 3.14.3, pip 26.1.2, exact dependency pins, `pip check`, documentation
  validation, and the full suite passed: `346 passed, 7 skipped, 1 warning` in
  74.74 seconds. The warning was a non-failing inability to update the
  sandbox-owned `.pytest_cache`; collection and tests completed.
- `.venv\Scripts\python.exe -m pytest --collect-only -q -p no:cacheprovider -m w6_inference_gate`
  — 10 selected out of 353 tests, exit 0.
- `.venv\Scripts\python.exe -m pytest --collect-only -q -p no:cacheprovider -m w7_production_gate`
  — 170 selected out of 353 tests, exit 0.
- `.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider app/tests/test_prediction_admission_postgres.py`
  — four skipped because `VDDAI_TEST_POSTGRES_DATABASE_URL` is not configured.
- `.venv\Scripts\python.exe -m black --check --workers 1 <13 changed Python files>`
  with an OS-temporary Black cache — all 13 files would be left unchanged.
- Direct in-process boundary probe with `MAX_IMAGE_PIXELS=100000000` and a
  checked synthetic `10000 x 10000` PNG header — upload returned safe `413` and
  preprocessing raised safe `ImagePreprocessingError`, demonstrating
  `VDDAI-REV-004` without allocating the declared image.

## Checks not run

- The PostgreSQL concurrency test was not executed because no explicitly
  disposable PostgreSQL 16 URL was configured. Its skip is not positive
  concurrency evidence.
- Docker services, the deployed production gate, the data-creating real
  inference probe, and Alembic upgrade/downgrade were not run. This remediation
  changes no Compose definition, schema, migration, registry selection, model
  package, or deployed artifact, and no disposable stack was authorized.
- Repository-wide Black was not rerun because the root instructions document
  pre-existing baseline drift; every changed Python file was checked.
- No model registration, promotion, rollback, artifact regeneration,
  deployment, commit, push, merge, or persistent-data deletion occurred.

## Ordered remediation handoff

1. `VDDAI-REV-004`: obtain human confirmation of the supported configurable
   upper bound, make configuration validation and Pillow behavior implement one
   exact-boundary contract, update the focused tests and affected current
   documentation, then rerun formatting, docs validation, and the canonical
   gate.
2. `VDDAI-REV-002`: provision an explicitly disposable PostgreSQL 16 test URL
   and run the existing four-test integration file. Change code only if the
   equal-email race does not yield one `201`, one `409`, and one row.
3. Re-review only the bounded remediation and fresh PostgreSQL evidence. After
   Reviewer eligibility, route the subject to independent VDDAI QA before the
   human commit/merge gate.

## Residual risks and assumptions

- The approved 16,777,216 default remains below Pillow's warning threshold, so
  `VDDAI-REV-004` is fail-closed and does not expose the default production path
  to oversized decoding.
- The PostgreSQL route logic follows SQLAlchemy's required rollback sequence,
  and its unit tests pass, but simultaneous transaction behavior remains
  unverified in this environment.
- The seven canonical skips are optional PostgreSQL-dependent tests, not
  production-readiness evidence.
- The maintained W7 production risk register remains authoritative; this
  remediation does not clear ingress/spooling, local-storage, retention,
  external artifact, rollback, probe-data, secret, or monitoring risks.
- Passing review checks does not authorize QA bypass, model promotion,
  deployment, commit, merge, or release.
