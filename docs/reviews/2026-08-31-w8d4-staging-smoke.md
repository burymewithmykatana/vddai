# W8D4 Staging Smoke Review

- Review ID: `W8D4-REV-2026-08-31-001`
- Date: 2026-08-31
- Task: W8D4 — Add deployment smoke test and rollback
- Base / HEAD / merge base: `1b9f6160883361bdb99298b256815197ccab8eba`
- Branch: `codex/w8d4-smoke-rollback`
- Subject: uncommitted `scripts/smoke_staging.py` and `app/tests/test_smoke_staging.py`; this report is audit-only.

## Contract sources and acceptance criteria

Reviewed the human-approved W8D4 handoff, root and application `AGENTS.md`,
ADRs 0007, 0008, and 0014, `scripts/prove_real_inference.py`, the existing
inference-contract tests, and production-readiness guidance. The subject must
provide health, authentication, upload, queue, inference, persistence, and
owner-read smoke evidence after staging deployment, define rollback to explicit
application and model versions, and preserve the existing W7 disposable-only
probe and registry-promotion policy.

## Verdict

**PASS** for the repository implementation subject. Live staging smoke and the
rollback rehearsal remain external execution evidence, not a claim made by this
review.

## Findings

No actionable findings.

The new staging client verifies HTTPS-origin syntax and exact staging/model
identity before registering probe users. It then exercises the existing
authenticated API and validates ownership, queue completion, persisted owner
history, selected-package stability, and frozen result semantics. It does not
alter the W7 probe, registry state, application/worker behavior, or model
artifacts. Failure messages are stable and do not include credentials or
private health fields.

## Acceptance-criteria coverage

| Criterion | Evidence | Result |
|---|---|---|
| Automated health/auth/upload/queue/inference/persistence/read smoke checks | `scripts/smoke_staging.py`, focused tests, inherited inference-result validators | Satisfied in repository; live evidence pending |
| Define rollback to previous application and model versions | Existing ADRs 0007, 0008, 0014 and production-readiness guidance retain explicit version/backup prerequisites | Documentation synchronization pending QA |
| Perform and document a rollback rehearsal | Requires a real staging host, release identities, backups, and separate human execution authority | External gate pending |

## Checks run

```powershell
.\.venv\Scripts\python.exe -m pytest -q app/tests/test_smoke_staging.py app/tests/test_prove_real_inference.py
```

Result: 28 passed.

```powershell
$env:PYTEST_ADDOPTS = '--basetemp=C:\\Temp\\vddai-w8d4-verify'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\\scripts\\verify.ps1 -IncludeFormatting -IncludeDockerConfig
```

Result: 423 passed, 7 skipped; Docker Compose configuration passed. The
explicit disposable pytest base avoids an unrelated inaccessible shared pytest
temporary directory.

```powershell
.\.venv\Scripts\python.exe scripts/graphify_repository.py build
git diff --check
```

Result: fresh graph at the reviewed base; no whitespace errors.

## Checks not run

No live staging endpoint, exact image digests, approved artifacts, model
identity, or operator access was available. Consequently no deployment, model
promotion/rollback, destructive migration, or live rollback rehearsal ran.

## Ordered remediation handoff

No code remediation is required. After QA, Documentation should add the
operator-facing W8D4 invocation and rollback/rehearsal guidance only when QA
can truthfully establish the reviewed implementation evidence. A live rehearsal
requires explicit human authorization and the prerequisites named above.

## Residual risks and assumptions

The smoke script intentionally retains probe-created users, prediction history,
and uploaded input; current retention policy governs them. It does not verify a
container image digest because HTTP health has no image-identity field; the
operator must record Docker inspection evidence as prescribed by the approved
handoff. Automated rollback remains out of scope.

## Process-learning evidence

- Observation: repository smoke verification can be independent of live staging execution when the external target is unavailable.
- Evidence: `app/tests/test_smoke_staging.py`, W8D4 handoff, and this review.
- Impact: preserves a testable client boundary without claiming deployment evidence.
- Recurrence: first observed.
- Candidate improvement: None.
- Authority note: this evidence does not authorize a skill or workflow change.
