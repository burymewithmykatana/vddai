# W8D4 staging smoke re-review R4

- **Review ID** `W8D4-REV-2026-11-21-004`
- **Date** 2026-11-21
- **Role** Independent VDDAI Reviewer
- **Task** W8D4 — Add deployment smoke test and rollback
- **Branch** `codex/w8d4-smoke-rollback`
- **Base, HEAD, and merge base** `1b9f6160883361bdb99298b256815197ccab8eba`
- **Approved remediation** `VDDAI-REV-002`, `VDDAI-REV-003`, and `VDDAI-REV-004`
- **Prior reports** [Initial review](2026-08-31-w8d4-staging-smoke.md),
  [R2](2026-08-31-w8d4-staging-smoke-r2.md), and
  [R3](2026-11-21-w8d4-staging-smoke-r3.md).

The implementation subject is the two remediated Python files. The index is
empty. The existing operator-guide draft is context for acceptance and
Documentation handoff. The local `vddai-artifacts.tar.gz` is excluded.

| File | Reviewed SHA-256 |
|---|---|
| `scripts/smoke_staging.py` | `6bbf359e0ba4898b4212e3a5ee2eafb9cf42726783638b3df2bcc9b14250dbe3` |
| `app/tests/test_smoke_staging.py` | `3b9153c91b08c5df5a296086394ace1f6848a8c68052acb7ceecb3daececcad5` |
| Existing `docs/engineering/production-readiness.md` draft | `cb691826e3c57181d7057cc29ab01d4ba0c6d11136b37fc9e766bac9d1bd0d3e` |
| Initial review | `7bfe6ffac60adcac2651c59a3fd4b08a016e64bf7deb4e111863b9c61b271df3` |
| R2 | `94237aa60d7d1602bf24ad8109a1d20b87066ac154c9dd1e1dc6426f83e75190` |
| R3 | `17902699595704ab3884d807947ada1eb2bca2c6bd7ba27b37030541703abbe4` |

## Contract sources and acceptance criteria

The W8D4 task calls for health, authentication, upload, queue, inference,
persistence, and result-read checks after deployment. It requires a definition
of rollback to previous application and model versions, one performed and
documented rehearsal, automated smoke and procedure evidence, tests,
documentation, and a visible commit. The release gate is deferred until the
staging server is available, and the task permits Week 9 to begin first.
The approved rehearsal is an application rollback with stable model selection.
[W8D4 task](https://app.notion.com/p/3ac0ab50ef678177a31ed823994298a9).
[R3 acceptance matrix](2026-11-21-w8d4-staging-smoke-r3.md#acceptance-criteria-coverage).

This re-review checks the exact human-selected remediation against R3's
closure criteria. The repository-approved contract uses a staging-only HTTPS
client with two existing dedicated accounts, one upload, a protected external
state directory, operator-controlled reconciliation, and a safe evidence
receipt. The review verified the changed boundaries against the prior task,
repository instructions, and authoritative persistence and deployment contracts.
[Root instructions](../../AGENTS.md). [Application instructions](../../app/AGENTS.md).
[Documentation index](../README.md). [Catalog](../catalog.yaml).
[Agent workflow](../engineering/agent-workflow.md).
[ADR 0003](../decisions/0003-production-inference-contract.md).
[ADR 0005](../decisions/0005-inference-result-persistence.md).
[ADR 0007](../decisions/0007-controlled-model-registry.md).
[ADR 0008](../decisions/0008-registry-selected-production-package.md).
[ADR 0009](../decisions/0009-durable-image-storage-boundary.md).
[ADR 0010](../decisions/0010-database-backed-prediction-reliability.md).
[ADR 0011](../decisions/0011-database-backed-prediction-admission.md).
[ADR 0012](../decisions/0012-immutable-application-image-publication.md).
[ADR 0014](../decisions/0014-single-host-staging-environment.md).

## Verdict

**CHANGES REQUIRED** for full W8D4 acceptance. All three approved code findings
are verified resolved. The live HTTPS smoke and independently attributable
rehearsal evidence required by VDDAI-REV-001 remain outstanding. The current
subject is ineligible for QA and Documentation.

## Findings

### VDDAI-REV-001 — Required live deployment and rollback evidence remains unverified

**HIGH · STILL OPEN**

- **Location** W8D4 task DoD and `docs/engineering/production-readiness.md`
  lines 249–274 and 311–317.
- **Evidence** R3 records the recovered checklist and operator-reported
  successful isolated application rollback and roll-forward. No newer
  phase-by-phase rehearsal record, deployment-linked registry evidence, or
  passing live HTTPS smoke report was supplied with this remediation. The
  known smoke JSON still records a preflight failure. The successful GHCR jobs
  establish candidate publication. The Docker Desktop backup checks support
  recovery of that historical snapshot. Neither record identifies the exact
  running API and worker images on the intended live host. [R3 operational evidence](2026-11-21-w8d4-staging-smoke-r3.md#vddai-rev-001--required-live-deployment-and-rollback-evidence-remains-unverified).
- **Impact** The available record leaves the actual HTTPS ingress, running
  application identity, and recovery of durable work unverified.
- **Required action** The environment owner supplies the existing rehearsal
  record and available evidence for its missing phases. Preserve the operator's
  reported success. Outstanding server-dependent checks stay at the deferred,
  separately authorized live release gate.
- **Closure check** Independently verify a passing HTTPS smoke report and
  dated application rehearsal record tying the before, failure, and recovery
  phases to both exact application digests, compatible schema and backups,
  stable registry/package identity, the recovered queued test job, and the
  retained completed owner read. Record the distinct previous digest and the
  scope of the transition performed.

### VDDAI-REV-002 — The pending reservation lacks crash-durable directory entries

**MEDIUM · VERIFIED RESOLVED**

- **Location** `scripts/smoke_staging.py` lines 240–286, 364–370, and 402–448.
  Closure tests are in `app/tests/test_smoke_staging.py` lines 434–582.
- **Evidence** The POSIX path syncs the `run.json` file and its pending
  directory entry, then syncs the state directory containing the reservation
  name before the sole prediction POST. After the ID is known, it syncs
  `prediction.json` and the containing pending directory. The Windows path
  publishes the pending directory with a same-volume `MoveFileExW` write-through
  move. It syncs each JSON file, then publishes it with the same write-through
  flag and no replace or cross-volume copy flag. Failure before durable
  reservation or run metadata stops before POST. Failure persisting the ID
  after POST reports the known ID and keeps the reservation blocking re-entry.
  [Linux fsync(2)](https://man7.org/linux/man-pages/man2/fsync.2.html).
  [Microsoft MoveFileExW](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-movefileexw).
- **Closure verification** Independently ran the focused suite on Windows,
  including native publication order, all three injected publication failure
  points, competing reservation, fsync failure, fresh-interpreter recovery of
  the marker and saved ID, and the one-upload guard. Inspected POSIX filesystem
  ordering and Coder-reported execution of the corresponding native tests on
  disposable Linux. Evidence covers the documented filesystem operations and
  process restart; power-loss behavior was evaluated from the platform APIs.

### VDDAI-REV-003 — Operator interruption can leave a blank evidence receipt

**MEDIUM · VERIFIED RESOLVED**

- **Location** `scripts/smoke_staging.py` lines 517–575, 578–611, and 689–721.
  Closure tests are in `app/tests/test_smoke_staging.py` lines 754–929.
- **Evidence** The supervisor explicitly kills and waits for its child after
  catchable cancellation or timeout before reading the run-matched pending
  record. A second interruption during reaping retries the stop and wait.
  The CLI owns the same run ID when handing off to the supervisor and can
  recover the saved ID and cleanup status if cancellation occurs at return
  or first report finalization. The receipt records a stable failure code and
  nonzero exit while the reservation continues to block an unresolved retry.
- **Closure verification** Independently ran the pre-reservation, ambiguous
  upload, known-ID, repeated interruption, supervisor handoff, and report
  write cases. All passed. An additional local synthetic check used a real
  Windows child with the production supervisor and an offline child payload.
  Timeout and simulated cancellation both reaped the child before recovery,
  returned their stable failure codes, and recovered the matching ID.

### VDDAI-REV-004 — Owner history can pass with a mismatched JSON type

**MEDIUM · VERIFIED RESOLVED**

- **Location** `scripts/smoke_staging.py` lines 302–328 and 479–501. Closure
  tests are in `app/tests/test_smoke_staging.py` lines 194–224 and 384–406.
- **Evidence** The owner history must contain exactly one item. That item
  passes the prediction and identity contract before the initial, fresh, and
  historical results are compared as deterministic compact JSON with nonfinite
  values rejected. This preserves JSON value types, including nested lineage
  fields, across the comparison.
- **Closure verification** The independent focused run passed the valid
  matching history case and reproduced the original `true` versus `1`
  substitution as a stable `persisted_result_changed` failure. Additional
  cases cover a boolean history score, a nested lineage integer, and the
  nested-type mismatch in the fresh result.

The reviewed remediation produced no new actionable finding.

## Acceptance-criteria coverage

| Criterion | Current evidence and status |
|---|---|
| Staging and model identity, health, authentication, and owner isolation | The repository client checks the gated HTTPS origin, service/database/model health, dedicated accounts, and the exact non-disclosing cross-owner and missing response. Focused regression checks passed. Live HTTP and account evidence remain part of VDDAI-REV-001. |
| Upload, queue, and real-worker inference | The client reserves durable local state before the sole synthetic upload, checks accepted queue identity, and reads the frozen completed result through the existing API. VDDAI-REV-002 is resolved. Live end-to-end worker evidence remains pending. |
| Persistence, result read, and safe evidence | Exact typed read/history matching, safe cancellation evidence, and the operator reconciliation boundary passed the focused checks. VDDAI-REV-003 and VDDAI-REV-004 are resolved. |
| Define previous application and model rollback | The guide draft retains explicit previous application digest and audited model rollback definitions. Its smoke invocation, dedicated account roles, and reconciliation checkpoints still need authorized lifecycle synchronization after QA. |
| One performed and documented rehearsal and automated live evidence | Operator-reported isolated rollback and roll-forward are retained. Live smoke and the dated execution record remain open under VDDAI-REV-001. |
| Tests, documentation, visible commit | The exact remedy has independent focused evidence and full Coder checks. Final Documentation and the scoped commit remain pending. |

## Checks run

- `git status --porcelain=v1 --untracked-files=all`, `git branch --show-current`,
  `git rev-parse HEAD`, `git merge-base HEAD master`, `git diff --cached --stat`,
  and `Get-FileHash -Algorithm SHA256 -LiteralPath` established the range and
  the six file hashes above. `git diff --check` passed for the tracked draft.
- Pinned Windows focused verification reported **105 passed in 15.98 s**.

  ```powershell
  $vddaiPinned = 'C:/Users/S.R.G/AppData/Local/Temp/vddai-w8d4-portable-f21215c20b9c4305be685aa56e1b3e31/runtime/python.exe'
  & $vddaiPinned --version
  $env:PYTHONDONTWRITEBYTECODE = '1'
  & $vddaiPinned -m pytest -q -p no:cacheprovider --basetemp "$env:TEMP/vddai-w8d4-r4-review-$PID" app/tests/test_smoke_staging.py app/tests/test_prove_real_inference.py
  ```

- `& $vddaiPinned -` ran two offline real-child supervisor scenarios. A short
  substitute child persisted a synthetic reservation and ID 1, then blocked.
  The production supervisor exercised `deadline_exceeded` on timeout and
  `operator_interrupted` with injected `KeyboardInterrupt` after actual child
  communication. Both verified that the child was reaped before the recovery
  callback and that ID 1 and its matching run survived in the receipt.
  Temporary state was outside the repository.
- `& $vddaiPinned scripts/validate_docs.py` passed before adding this report
  with 25 canonical documents and 73 Markdown files.

### Coder-reported checks for the same hashes

- Pinned `python -m pytest -q app/tests/test_smoke_staging.py app/tests/test_prove_real_inference.py`
  reported 105 passing on Windows and 105 on disposable Linux with network
  access disabled. The first runs had a single real-child startup time
  failure at the five-second test budget. The passing runs provide the new
  real-process cases a 60-second fixture budget and preserve the production
  deadline and separate short timeout regression.
- `./scripts/verify.ps1 -PythonCommand $W8D4Python -IncludeFormatting` reported
  pinned dependencies, formatting, documentation, Alembic head `20260821_04`,
  and 507 tests passing on disposable PostgreSQL 16.15.
- `python scripts/run_production_gate.py` reported 171 passed and 336
  deselected against the same disposable database. Coder removed the test
  database and Linux container after verification.

## Checks outside the independent review run

Independent execution used local Windows filesystem and child-process checks.
Linux, canonical, and PostgreSQL integration results above are Coder evidence
for the exact remediated bytes. The review used direct source inspection and
documented filesystem semantics for the power-loss boundary. Live HTTPS smoke
and rollback execution remain at the authorized operational gate. The
recovered evidence was carried forward from R3.

## Ordered handoff

1. Preserve R3 and R4 with their reviewed hashes. The approved Coder findings
   `VDDAI-REV-002` through `VDDAI-REV-004` require no further remediation on
   this subject.
2. Route `VDDAI-REV-001` to the environment owner for the existing rehearsal
   record and documented live release evidence. Preserve the isolated
   rollback and roll-forward and use the closer evidence when available.
3. Independently re-review the outstanding operational criterion against
   the exact current subject. QA requires an eligible current review, and
   Documentation follows QA `PASS`. Carry the existing guide synchronization
   in R3 to that later Documentation gate, then retain the human decision
   on the merge subject.

## Residual risks and assumptions

- A fixed protected operator state directory on a filesystem honoring the
  reviewed synchronization operations is a prerequisite. Matching pending
  state is the source for operator reconciliation when the request outcome is
  ambiguous. The fault-injection and real-process checks covered catchable
  cancellation and timeout.
- The definition of model rollback retains the separate human gate and
  explicit previous registry selection. The historical Docker Desktop
  snapshot has no established linkage to the deployed registry.
- The outstanding operational evidence remains an unmet W8D4 criterion even
  though the project schedule allows later work to begin.

## Process-learning evidence

- **Observation** The closure checks separated native publication ordering,
  process restart visibility, and cancellation of an active child.
- **Evidence** VDDAI-REV-002 and VDDAI-REV-003, the 105-test focused rerun,
  and the supplementary real-child checks recorded above.
- **Impact** The evidence supports the scoped closures while recording the
  limits of power-loss and live-release verification.
- **Recurrence** Unknown.
- **Candidate improvement** None.
- **Authority note** This evidence carries no authority to change a skill or
  workflow or to approve remediation.
