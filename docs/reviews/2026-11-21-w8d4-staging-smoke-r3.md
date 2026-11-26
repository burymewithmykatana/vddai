# W8D4 staging smoke re-review

- **Review ID** `W8D4-REV-2026-11-21-003`
- **Date** 2026-11-21
- **Role** Independent VDDAI Reviewer
- **Task** W8D4 — Add deployment smoke test and rollback
- **Branch** `codex/w8d4-smoke-rollback`
- **Base, HEAD, and merge base** `1b9f6160883361bdb99298b256815197ccab8eba`
- **Prior reports** [Initial review](2026-08-31-w8d4-staging-smoke.md) and
  [second review](2026-08-31-w8d4-staging-smoke-r2.md).

The current implementation subject is the uncommitted staging client and its
tests. The existing operator-guide draft was inspected for coverage and
handoff dependencies. The index had no staged changes. The local
`vddai-artifacts.tar.gz` is outside the implementation and review subject.

| File | SHA-256 at review |
|---|---|
| `scripts/smoke_staging.py` | `2330e49af94540a49bb9fc6bbb653b88a2f8bedb6873341e0fa7035380cf79ae` |
| `app/tests/test_smoke_staging.py` | `0f600c6bb748938c3525edbf2f53db8da669be9051f97a8bb85d63f59dcf22a3` |
| `docs/engineering/production-readiness.md`, existing draft | `cb691826e3c57181d7057cc29ab01d4ba0c6d11136b37fc9e766bac9d1bd0d3e` |
| Initial review | `7bfe6ffac60adcac2651c59a3fd4b08a016e64bf7deb4e111863b9c61b271df3` |
| Second review | `94237aa60d7d1602bf24ad8109a1d20b87066ac154c9dd1e1dc6426f83e75190` |

## Contract sources and acceptance criteria

The task requires post-deploy health, authentication, upload, queue,
inference, persistence, and result-read checks. It also requires a definition
of rollback to the previous application and model versions, one performed and
documented rollback rehearsal, automated smoke evidence, a tested procedure,
tests, documentation, and a visible commit. The September 9 Notion status
defers live execution until the short-lived staging server is available and
allows Week 9 to begin beforehand. The task body still lists the live checks
and rehearsal evidence as completion criteria. [W8D4 task](https://app.notion.com/p/3ac0ab50ef678177a31ed823994298a9).

The approved Planner and Coder handoffs define the staging-only client, two
dedicated pre-existing active non-administrator accounts, explicit identities,
one synthetic image, a protected external state directory, a durable
reservation for the single upload, and operator-only reconciliation. The
approved rehearsal scope is an application rollback with stable model
selection. An actual model rollback has its own approval and explicit registry
target under the accepted design. [Repository instructions](../../AGENTS.md).
[Application instructions](../../app/AGENTS.md).
[Agent workflow](../engineering/agent-workflow.md).
[Documentation index and authority order](../README.md).
[Documentation catalog](../catalog.yaml).

Contract inspection covered authenticated routes, both application health
identities, queue admission and worker settlement, the frozen prediction and
lineage schemas, the W7 disposable probe, and the exact image-publication and
staging launch boundaries. [ADR 0003](../decisions/0003-production-inference-contract.md).
[ADR 0005](../decisions/0005-inference-result-persistence.md).
[ADR 0007](../decisions/0007-controlled-model-registry.md).
[ADR 0008](../decisions/0008-registry-selected-production-package.md).
[ADR 0009](../decisions/0009-durable-image-storage-boundary.md).
[ADR 0010](../decisions/0010-database-backed-prediction-reliability.md).
[ADR 0011](../decisions/0011-database-backed-prediction-admission.md).
[ADR 0012](../decisions/0012-immutable-application-image-publication.md).
[ADR 0014](../decisions/0014-single-host-staging-environment.md).

## Verdict

**CHANGES REQUIRED**. The required live release evidence remains unverified
under VDDAI-REV-001. Three implementation defects affect the reservation,
cancellation evidence, and readback comparison. The current review is
ineligible for QA and Documentation under the maintained workflow.

## Findings

### VDDAI-REV-001 — Required live deployment and rollback evidence remains unverified

**HIGH · STILL OPEN**

- **Location** W8D4 task DoD and
  `docs/engineering/production-readiness.md` lines 249–274 and 311–317.
- **Evidence** The operator recovered the checklist and reports successful
  isolated application rollback and roll-forward. The reviewed material
  contains no dated, phase-by-phase record tying that success to a passing
  HTTPS staging run, the deployed API and worker images, or recovered and
  retained prediction reads. The only known smoke JSON,
  `D:/VDDAI-local/missing-staging-preflight-20260831.json`, records `FAIL` at
  `preflight` with `invalid_staging_origin` and zero passed stages. Both
  immutable GHCR publication steps succeeded. The handoff matches the
  published digests to the saved candidate settings and records blank
  deployment fields. Publication supplies candidate identities. Actual
  deployment identity is still unverified. [Publication job 99454498780](https://github.com/burymewithmykatana/vddai/actions/runs/33381202527/job/99454498780).
  [Publication job 99337654739](https://github.com/burymewithmykatana/vddai/actions/runs/33341298801/job/99337654739).
- **Backup scope** The historical Docker Desktop recovery manifest at
  `D:/VDDAI-local/backups/w8d4-20260831/manifest.json` has SHA-256
  `f326c1436a3a11c0f0a26771f7426e8739ea092c5d27ca1044dbf23561f6c803`.
  Prior planning verified five component hashes and matched registry snapshots
  with one selected version and empty rollback pointers. The reviewed material
  leaves the link between that snapshot and any live staging deploy unverified.
- **Impact** Closing the task from the available evidence would leave the
  deployed HTTPS ingress, exact running images, and recovery of durable work
  unverified.
- **Required action** The environment owner supplies the recovered rehearsal
  record and adds existing evidence for its missing phases where available.
  Preserve the reported isolated success and use its record for re-review.
  Remaining server-dependent evidence stays deferred to the authorized live
  release gate.
- **Closure check** Independently verify a passing HTTPS smoke report and the
  dated operator record of the approved application rehearsal. Bind the
  before/failure/recovery smoke results to the exact API and worker digests,
  compatible schema and backups, unchanged registry/package identity,
  recovery of the queued test job, and the retained completed owner read. Keep
  the previous distinct application digest explicit. The rehearsal record
  must match the scope of the application transition that was performed.

### VDDAI-REV-002 — The pending reservation lacks crash-durable directory entries

**MEDIUM · OPEN**

- **Location** `scripts/smoke_staging.py` lines 240–249 and 327–333, 367–389,
  402–408.
- **Evidence and failure scenario** The restart guard depends on finding the
  `w8d4-pending` directory. The client creates it and syncs the contents of
  `run.json` before uploading. On Linux, syncing a file descriptor can leave
  the parent's new directory entry uncommitted. The state directory and
  pending directory have no corresponding durability check. A local operator
  host crash around upload therefore leaves no guarantee that the reservation
  is visible on restart or that a saved `prediction.json` remains discoverable.
  [Linux fsync(2) documentation](https://man7.org/linux/man-pages/man2/fsync.2.html).
- **Impact** Losing the reservation can bypass operator reconciliation. Empty
  account histories are insufficient to establish the outcome when the earlier
  HTTP request is unresolved or a stored object lacks a corresponding row.
- **Required action** Durably persist the reservation and its metadata entries
  through the supported filesystem boundary before issuing the upload. Treat
  a failed persistence step as a pre-POST failure. Preserve the same durable
  lookup for the known prediction ID once received.
- **Closure check** Exercise ordering of the durable steps before POST,
  failure of the directory persistence step with zero uploads, and restart
  discovery of the reservation and a known ID. Use local disposable state or
  deterministic failure injection on the applicable client platforms.

### VDDAI-REV-003 — Operator interruption can leave a blank evidence receipt

**MEDIUM · OPEN**

- **Location** `scripts/smoke_staging.py` lines 478–512 and 613–644.
- **Evidence and failure scenario** The supervisor handles a subprocess timeout
  and ordinary process failures. A `KeyboardInterrupt` escapes both the
  supervisor and the CLI finalization. In a local synthetic check, the simulated
  child saved prediction ID 1, then the interruption propagated through
  `main()`. The evidence file remained zero bytes and `prediction.json` still
  existed.
- **Impact** A cancellation during an ambiguous upload can leave the operator
  without the stable failure stage, known prediction ID, or cleanup status in
  the evidence receipt. The pending directory continues to prevent another
  upload when it is present.
- **Required action** Handle a catchable operator cancellation in the CLI
  supervisor, ensure the child has stopped before making cleanup status
  available, recover the matching reservation and saved ID when present, and
  finalize a nonzero sanitized evidence result. Preserve the queued-data
  reconciliation boundary.
- **Closure check** Exercise cancellation before reservation and after an
  upload attempt with and without a saved ID. Verify valid failure JSON,
  correct cleanup status, no traceback in the CLI output, and no resubmission
  while the reservation remains.

### VDDAI-REV-004 — Owner history can pass with a mismatched JSON type

**MEDIUM · OPEN**

- **Location** `scripts/smoke_staging.py` lines 265–289 and 439–452.
- **Evidence and failure scenario** The two resource reads validate the
  prediction identity as an integer and check the result contract. The client
  compares the history to the validated result using Python object equality
  alone. In a local synthetic response, the owner history contained boolean
  `true` as its ID and both resource reads contained integer `1`. Python
  considered the values equal, so the gate recorded `persistence_readback`
  passed and emitted `PASS`.
- **Impact** A serialization regression can give clients malformed owner history
  while the smoke evidence claims that history matches a fresh valid read.
- **Required action** Validate the owner history item through the prediction
  contract and use a comparison that preserves relevant JSON types across
  the fresh result and history. Keep the exact one-record expectation.
- **Closure check** Verify that a valid identical read/history pair succeeds
  and that a mismatched history ID type or other boolean/number substitution
  fails persistence readback with a stable failure code.

## Acceptance-criteria coverage

| Criterion | Traced implementation and evidence | Status |
|---|---|---|
| Health and explicit staging/model identity | HTTPS hostname guard and TLS verification precede credentials. The client checks `/health`, `/health/db`, and ADR 0008 registry version/package identity before and after the flow. Focused transport and identity tests passed. | Repository behavior verified with synthetic inputs. Live staging evidence pending. |
| Authentication and owner isolation | The client uses two configured identities, checks the authenticated JWT subject and empty histories, and exercises the non-disclosing cross-owner and missing `404`. Active-user and owner checks stay in the application API. Non-admin role is an operator precondition. | Repository behavior verified with synthetic inputs. Live role and HTTP evidence pending. |
| Upload, queue, and inference | Reused deterministic 64×64 PNG, one `POST /predictions`, HTTP `202` with positive ID and queued status, then existing HTTP lifecycle reads. ADRs 0010 and 0011 connect those routes to PostgreSQL and the worker's terminal settlement. Completed results pass the frozen label, package, lineage and timestamp contract. | Repository path traced and focused tests passed. Live completion and durable-reservation closure pending. |
| Persistence, result read, and safe evidence | The client uses a fresh owner read, owner history, selection recheck, and safe JSON receipt. The supervisor covers timeouts and retains a pending marker for operator reconciliation. | Exact history type and cancellation handling require VDDAI-REV-003 and VDDAI-REV-004. |
| Define rollback to previous application and model versions | Operator-guide draft specifies distinct compatible application digests and the audited `ModelRegistry.rollback` interface checked against ADRs 0007, 0008, 0012, and 0014. | Definitions present in draft. Synchronization with the eligible implementation remains open. |
| Perform and document a rehearsal and retain automated post-deploy evidence | Recovered checklist and operator-reported isolated rollback and roll-forward, two verified publication steps, historical recovery backup, and the preflight failure JSON. | VDDAI-REV-001 remains open. Passing HTTPS smoke and the dated execution record are still needed. |
| Tests, documentation, and a visible commit | Both Python files match the handed-off hashes. The guide is an existing working-tree draft and the implementation is uncommitted. | Focused tests pass. Final documentation and scoped commit remain pending. |

## Checks run

- `git status --short --branch`, `git status --porcelain=v1 --untracked-files=all`,
  `git rev-parse HEAD`, `git merge-base HEAD master`, `git diff --cached --stat`,
  and `git diff -- docs/engineering/production-readiness.md` confirmed the
  review range. The two untracked Python files were read in full. SHA-256
  with `Get-FileHash -Algorithm SHA256 -LiteralPath` confirmed all five file
  identities listed above and the historical backup manifest.
- Independently verified the focused suite with the isolated pinned interpreter.
  The command reported **89 passed in 13.69s**.

  ```powershell
  $vddaiPinned = 'C:/Users/S.R.G/AppData/Local/Temp/vddai-w8d4-portable-f21215c20b9c4305be685aa56e1b3e31/runtime/python.exe'
  & $vddaiPinned --version
  $env:PYTHONDONTWRITEBYTECODE = '1'
  & $vddaiPinned -m pytest -q -p no:cacheprovider --basetemp "$env:TEMP/vddai-w8d4-review-20261121-$PID" app/tests/test_smoke_staging.py app/tests/test_prove_real_inference.py
  ```

- `& $vddaiPinned -` with two synthetic `Scenario` cases from
  `app/tests/test_smoke_staging.py` reproduced VDDAI-REV-003 and VDDAI-REV-004.
  Temporary state was outside the workspace and the mocked transport used no
  remote endpoint. The interruption propagated with a zero-byte receipt and
  saved prediction ID. The boolean history ID produced `PASS`.
- `git diff --check` passed for the tracked draft. Direct source inspection
  included the untracked Python files and the new report is checked separately.
- `& $vddaiPinned scripts/validate_docs.py` passed before adding this report,
  covering 25 canonical documents and 72 Markdown files.
- Read the Notion task by page ID and queried GitHub Actions step metadata for
  jobs `99454498780` and `99337654739`. The build-and-publish step succeeded
  for both. Inspected only the preflight verdict, stage, error code, and stage
  count from the historical local JSON.

## Checks outside the review run

Coder reported 491 passing canonical tests with formatting and 171 passing
strict integration tests on disposable PostgreSQL 16.15, with 320
deselected, for the handed-off Python file hashes. Reviewer reran the focused
suite only. The disposable database used for Coder verification had already
been removed. Review used direct sources throughout.

Live HTTPS smoke, container inspection, rollback execution, and registry
changes were outside the authorized review actions. The operational evidence
check used the existing operator report and available records. Abrupt
host-loss behavior in VDDAI-REV-002 follows from source inspection and the
Linux synchronization contract. The review used synthetic interruption for
VDDAI-REV-003.

## Ordered remediation handoff

1. The human selects the implementation finding IDs for bounded Coder
   remediation in this report. VDDAI-REV-002, VDDAI-REV-003, and VDDAI-REV-004
   are independent changes with the closure checks above. Retain this report
   and both August 31 reports as immutable evidence.
2. In parallel, the environment owner supplies the existing phase record and
   passing HTTPS evidence for VDDAI-REV-001 or identifies the specific live
   evidence still awaiting the deferred release gate.
3. Independently re-review the resulting implementation hashes and the
   recovered operational record. An eligible current review is required
   before QA can verify the subject. Documentation follows QA `PASS`, then
   the proposed merge subject goes to the human decision.
4. At Documentation eligibility, synchronize the existing guide's invocation
   and reconciliation prerequisites. Lines 178–199 still show the earlier
   invocation and automatic registration. The current client requires
   `--accounts-file` and `--state-dir` and begins with empty dedicated
   account histories. Lines 251–273 need the reconciliation checkpoints
   between probe invocations and an independently retained completed record
   owned outside the two dedicated smoke accounts. Carry forward the
   requirements for separate authorization, exact terminal test rows,
   validated object identity, and retention of unresolved state.

## Residual risks and assumptions

- One fixed, access-restricted state directory coordinates one staging
  account pair. Its protection, exclusive operator use, and the accounts'
  current roles come from operator provisioning. The existing login API
  returns a token scoped to the user ID.
- Admission can consume a request-rate slot even on an upload failure. An
  interrupted upload can leave an unknown outcome. Unresolved state continues
  to require the operator's inspection of the exact test data boundary.
- Published GHCR digests and the historical backup do not establish the
  running application identity or live recoverability on a later staging
  host. Real registry rollback requires an independently approved prior
  selection and the existing validity gates.

## Process-learning evidence

- **Observation** Focused passing tests left the catchable cancellation path
  and JSON type differences in persistence comparison unexercised.
- **Evidence** W8D4-REV-2026-11-21-003, VDDAI-REV-003, VDDAI-REV-004, and the
  two synthetic source-boundary checks above.
- **Impact** The review found specific closure cases for stable operational
  evidence instead of inferring completeness from the aggregate count.
- **Recurrence** Unknown.
- **Candidate improvement** None.
- **Authority note** This evidence carries no authority to change a skill or
  workflow or to approve remediation.
