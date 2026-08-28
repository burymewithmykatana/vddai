# W8D1 CI Quality Gate Review

- Review ID: `W8D1-REV-2026-08-27`
- Date: 2026-08-27
- Task: W8D1 — Build the CI quality gate
- Base: `30d20abffd594757f12eef6ea08560f578119b4e`
- Subject: branch `codex/ci/w8d1-quality-gate`, `HEAD` equal to the base, with
  the complete implementation present as unstaged tracked changes and four
  relevant untracked files. No implementation commit exists.
- Scope: `.github/workflows/ci.yml`, verification/gate scripts and tests,
  maintained documentation, and the pull-request template. No runtime, schema,
  worker, ML, artifact, registry, or promotion implementation changes were in
  the subject.

## Contract sources reviewed

- Approved W8D1 request and its two amendments.
- Root `AGENTS.md`, `docs/README.md`, `docs/catalog.yaml`, and
  `docs/reviews/README.md`.
- Current `docs/engineering/production-readiness.md` and
  `docs/architecture/system-requirements.md`.
- Executable contracts in `scripts/verify.ps1`,
  `scripts/run_production_gate.py`, `pytest.ini`, `docker-compose.yaml`,
  `.env.example`, `Dockerfile`, the seven PostgreSQL tests, and the full
  working-tree delta.

## Verdict

**PASS WITH DOCUMENTED RISK**

The implementation satisfies the approved W8D1 behavior on source review and
the independently run local validator checks. The remaining risk is the
explicitly expected absence of a hosted Actions run; this review also did not
start a disposable PostgreSQL service, so it does not independently reproduce
the Coder's full PostgreSQL-backed test and strict-gate counts. This is
recorded as a non-defect limitation, not a waiver of the required hosted gate.

## Findings

No actionable implementation findings were identified.

### VDDAI-REV-001 — NOTE — Hosted execution and independent PostgreSQL evidence pending

- Status: `ACCEPTED RISK`
- Location: `.github/workflows/ci.yml:18-133`.
- Evidence: the branch has not been pushed and therefore has no GitHub Actions
  execution, as stated in the review request. The review independently
  collected the seven required PostgreSQL tests and verified the strict runner
  blocks when its URL is absent, but did not create a test database while
  acting under the review write/data boundary.
- Why it matters: only an Actions run can prove the GitHub-hosted Ubuntu,
  service-container, cache, Docker, and complete PostgreSQL execution path.
- Required action: none before review handoff; after an authorized push or PR,
  record the stable aggregate check and both upstream job results. QA should
  independently run the PostgreSQL-backed suite in a disposable PostgreSQL 16
  database.
- Closure verification: successful hosted `CI / VDDAI v0.1.0 quality gate`
  run, plus QA evidence for the disposable PostgreSQL 16 suite and strict
  runner.

## Acceptance-criteria coverage

| Approved criterion | Implementation and review evidence |
|---|---|
| PR, `master` push, and manual triggers; read-only permission | Workflow lines 3-11 define exactly those triggers and `contents: read`; no job widens it. |
| Aggregate is stable and fail-closed | `quality-gate` has the exact approved display name, `if: ${{ always() }}`, needs both mandatory jobs, and exits nonzero unless each `needs.*.result` is `success` (workflow lines 113-133). This covers failed, skipped, canceled, and timed-out upstream results. |
| PR security and no production boundary | No `pull_request_target`, `secrets`, GitHub environment, registry login/push, deployment command, or writable token was found. Checkout disables persisted credentials. The only database credentials are static test-only service values. |
| PostgreSQL-backed canonical verification | The verification job provisions `postgres:16` with a health check and a loopback disposable URL, then calls the repository-owned `verify.ps1` and strict gate (lines 23-42 and 86-97). The seven selected PostgreSQL tests were independently collected. |
| Exact dependency/documentation/test/Compose checks | `verify.ps1` retains its Python/pip/requirements/pip-check logic and now calls the documentation and one-head validators before full pytest; CI enables Docker Compose validation (lines 145-206). |
| One Alembic head | `validate_alembic.py` resolves the repository's `alembic.ini` and absolute script location, then rejects zero or multiple heads. Its focused tests cover zero/multiple counts; direct execution reported `20260821_04`. |
| Changed-Python Black only | The range resolver uses PR base SHA, push `before`, and parent-or-zero manual/root behavior. The Python validator uses NUL-delimited Git output, `ACMR` filtering, root containment, live-file filtering, and Black check mode. It includes untracked files only when no CI base is supplied. A changed legacy file is `M` and therefore checked; deletions are deliberately excluded. |
| Strict W7D4 PostgreSQL evidence | The strict runner hard-codes the current seven maintained nodeids, fails if any is absent, requires every dual `w7_production_gate`/`postgres_integration` test to execute, and fails skips. New dual-marked tests enter `required_nodeids` automatically. The actual collected inventory exactly matches the seven nodeids. |
| Separate image build without publication | The isolated `image` job checks out with no persisted credential and runs only `docker build --tag ...`; no publish/authentication exists. `.dockerignore` excludes the generated `.env` used only for Compose interpolation. |
| Documentation and scope | README counts are updated to 362/7/171; the maintained architecture and readiness documents state the aggregate semantics and distinguish CI from merge, release, deployment, and promotion approval. No generated artifacts, schema changes, or runtime changes were present. |

## Checks run

| Command | Outcome |
|---|---|
| `git -c safe.directory=D:/Codes/visual-defect-ai-backend diff --check 30d20ab...` | Passed; no whitespace errors. |
| `python -m pytest -q app/tests/test_run_production_gate.py app/tests/test_validate_alembic.py app/tests/test_validate_python_formatting.py` | Passed: `12 passed`; one pre-existing pytest cache warning. |
| `python scripts/validate_alembic.py` | Passed: exactly one head, `20260821_04`. |
| `python scripts/validate_docs.py` | Passed: 22 canonical documents and 54 Markdown files before this audit report was written. |
| `python scripts/validate_python_formatting.py` | Passed for the current dirty tree; selected the six changed/untracked Python files. |
| `python scripts/validate_python_formatting.py --base 30d20ab... --head HEAD` | Passed with no committed-range Python files, expected because `HEAD` remains the base and the implementation is unstaged. |
| `python scripts/run_production_gate.py` with `VDDAI_TEST_POSTGRES_DATABASE_URL` absent | Failed closed as required, exit 1 with the disposable-PostgreSQL requirement. |
| `python -m pytest --collect-only -q -m 'w7_production_gate and postgres_integration'` | Passed collection: exactly 7 of 362 tests, matching the hard-coded inventory. |
| `python -m black --check --diff scripts/validate_python_formatting.py` | Passed. |
| YAML parse plus structural assertions for `.github/workflows/ci.yml` | Passed; confirmed global read-only permission, the three jobs, and aggregate display name. |
| Static workflow security scan for `pull_request_target`, secrets, environments, registry login/push, and writable permissions | No prohibited construct found. |

## Checks not run

- Hosted GitHub Actions execution: unavailable because push/PR mutation is not
  authorized.
- Complete pytest suite against an independently provisioned PostgreSQL 16
  service and `scripts/run_production_gate.py` with that service: not run by
  this reviewer to preserve the review contract's no-data-mutation boundary.
- Docker Compose config and Docker image build: not independently run; both
  require local Docker daemon execution. Their commands and isolation were
  source-reviewed, and the Coder-provided local results remain untrusted until
  QA or hosted CI supplies fresh evidence.
- A default `verify.ps1` execution was started twice without PostgreSQL and
  reached the full pytest phase, but this execution interface did not preserve
  a final exit status after its output timeout; it is not counted as passed.

## Remediation handoff

No implementation remediation is required. The next ordered handoff is:

1. Obtain independent QA evidence using a disposable PostgreSQL 16 database,
   including the complete suite, strict W7D4 runner, Compose config, and image
   build.
2. After human authorization to open/push a PR, verify the hosted workflow's
   `verification`, `image`, and `VDDAI v0.1.0 quality gate` checks all succeed.
3. Keep merge, release, deployment, and production model promotion under their
   existing human approvals.

## Residual risks and assumptions

- The aggregate check can later be configured as required by branch protection,
  but W8D1 deliberately does not mutate branch protection.
- A manual dispatch compares against the selected commit's parent (or uses the
  all-zero root-commit path); routine PR and `master` push events provide their
  event-specific comparison refs. This is consistent with the approved
  changed-file Black policy rather than a prohibited repository-wide legacy
  formatting baseline.
- Static test-only PostgreSQL credentials are not production credentials. The
  service is job-scoped and the application tests create UUID-named schemas.
