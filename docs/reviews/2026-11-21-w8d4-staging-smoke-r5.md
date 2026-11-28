# W8D4 operational evidence re-review R5

- **Review ID** `W8D4-REV-2026-11-21-005`
- **Date** 2026-11-21
- **Role** Independent VDDAI Reviewer
- **Task** W8D4 — Add deployment smoke test and rollback
- **Branch** `codex/w8d4-smoke-rollback`
- **Base, HEAD, and merge base** `1b9f6160883361bdb99298b256815197ccab8eba`
- **Prior reports** [Initial review](2026-08-31-w8d4-staging-smoke.md),
  [R2](2026-08-31-w8d4-staging-smoke-r2.md),
  [R3](2026-11-21-w8d4-staging-smoke-r3.md), and
  [R4](2026-11-21-w8d4-staging-smoke-r4.md).
- **Scope** Operational evidence for VDDAI-REV-001 against the exact R4
  implementation. The user approved two dedicated non-admin staging accounts
  and one live HTTPS smoke invocation. This report reviews those records
  after execution. The Git index is empty and the local artifact tarball is
  excluded.

| File | Reviewed SHA-256 |
|---|---|
| `scripts/smoke_staging.py` | `6bbf359e0ba4898b4212e3a5ee2eafb9cf42726783638b3df2bcc9b14250dbe3` |
| `app/tests/test_smoke_staging.py` | `3b9153c91b08c5df5a296086394ace1f6848a8c68052acb7ceecb3daececcad5` |
| Existing `docs/engineering/production-readiness.md` draft | `cb691826e3c57181d7057cc29ab01d4ba0c6d11136b37fc9e766bac9d1bd0d3e` |
| Initial review | `7bfe6ffac60adcac2651c59a3fd4b08a016e64bf7deb4e111863b9c61b271df3` |
| R2 | `94237aa60d7d1602bf24ad8109a1d20b87066ac154c9dd1e1dc6426f83e75190` |
| R3 | `17902699595704ab3884d807947ada1eb2bca2c6bd7ba27b37030541703abbe4` |
| R4 | `1e7e67db11f6b4ea11f318caa5d68e67e1640c85a35a5899d4d2d1231ca22559` |

## Contract sources and acceptance criteria

W8D4 requires post-deploy health, authentication, upload, queue, inference,
persistence, and result-read checks, a definition of previous application and
model rollback, one performed and documented rollback rehearsal, and the
tested gate, documentation, and scoped commit. The approved rehearsal covers
application rollback with stable model selection. The separate model rollback
procedure uses the registry's explicit previous selection and guarded
transition. [W8D4 task](https://app.notion.com/p/3ac0ab50ef678177a31ed823994298a9).
[R4 acceptance matrix](2026-11-21-w8d4-staging-smoke-r4.md#acceptance-criteria-coverage).

The re-review applied the root and app instructions and maintained workflow.
The source checks included the exact R4 staging runner's health gate, two
subject-bound account logins, sole upload, history and owner isolation, and
typed result matching. The accepted contracts establish the digest-pinned
staging boundary and distinguish the registry model version from the package
ID persisted with a prediction. [Root instructions](../../AGENTS.md).
[Application instructions](../../app/AGENTS.md). [Documentation index](../README.md).
[Catalog](../catalog.yaml). [Agent workflow](../engineering/agent-workflow.md).
[ADR 0003](../decisions/0003-production-inference-contract.md).
[ADR 0005](../decisions/0005-inference-result-persistence.md).
[ADR 0007](../decisions/0007-controlled-model-registry.md).
[ADR 0008](../decisions/0008-registry-selected-production-package.md).
[ADR 0010](../decisions/0010-database-backed-prediction-reliability.md).
[ADR 0011](../decisions/0011-database-backed-prediction-admission.md).
[ADR 0012](../decisions/0012-immutable-application-image-publication.md).
[ADR 0014](../decisions/0014-single-host-staging-environment.md).

## Verdict

**CHANGES REQUIRED** for full W8D4 acceptance. The live HTTPS smoke
criterion is verified. VDDAI-REV-001 remains open for the dated, attributable
application rehearsal record. R4's verified closures remain current. QA and
Documentation remain ineligible under the maintained workflow.

## Findings

### VDDAI-REV-001 — Application rollback rehearsal evidence remains unverified

**HIGH · STILL OPEN**

- **Location** W8D4 task DoD and `docs/engineering/production-readiness.md`
  lines 214–274 and 311–317.
- **New evidence** The authorized R4 live HTTPS receipt records `PASS` through
  all seven stages on the digest-pinned deployment. The preserved request,
  PostgreSQL, pending-state, registry, and image records corroborate the
  receipt. The live smoke component of R4's closure check is satisfied.
- **Remaining evidence** The operator reports successful isolated
  application rollback and roll-forward, and recovered the checklist. The
  reviewed material still lacks a dated record tying the before, controlled
  failure, rollback, recovery, and roll-forward phases to exact running
  images, compatible database and backups, stable registry/package identity,
  recovery of accepted queued work, and owner readback of the retained
  completed result. The earlier authenticated inspection found no matching
  lifecycle events in the retained Docker event window and no attributable
  execution record in the searched sources. The isolated `vddai_restore`
  catalog had zero public/application tables when inspected. The successful
  current smoke and older database and backup facts now give attributable
  observations for their own windows.
- **Impact** W8D4 still lacks independently checkable proof connecting the
  reported application transition to recovery of durable work.
- **Required action and closure check** The environment owner supplies the
  existing dated rehearsal record or contemporaneous phase artifacts. Bind
  each phase to the current and previous API and worker image digests, schema
  and relevant backup identities, registry/package selection, queued-job
  recovery, and the retained completed owner read. Keep the operator-reported
  success in the record and review the evidence for the approved application
  rehearsal scope. No new execution is needed to review the existing record.

### VDDAI-REV-002 — Pending-reservation durability

**MEDIUM · VERIFIED RESOLVED**

The runner and tests match R4's reviewed hashes. The live `run.json` and
`prediction.json` bind the pending marker and saved prediction ID to the
receipt for this invocation. R4's local filesystem operation and failure
checks remain the closure evidence for crash durability. [R4](2026-11-21-w8d4-staging-smoke-r4.md).

### VDDAI-REV-003 — Catchable cancellation evidence

**MEDIUM · VERIFIED RESOLVED**

The exact R4 supervisor, tests, and offline real-child timeout/cancellation
checks remain the closure evidence. This completed live invocation supplies
its ordinary completion receipt. [R4](2026-11-21-w8d4-staging-smoke-r4.md).

### VDDAI-REV-004 — Type-exact owner-history readback

**MEDIUM · VERIFIED RESOLVED**

R4's exact runner/test hashes and typed mismatch regression checks still
establish the closure. The live run passed the runner's `persistence_readback`
stage with an identical typed result across the first read, second read, and
owner history. The recorded result fingerprint binds the client comparison.
[R4](2026-11-21-w8d4-staging-smoke-r4.md).

No new actionable code finding was identified in the operational evidence.

## Live evidence and provenance

The three sanitized records are retained outside Git under
`D:/VDDAI-local/evidence/w8d4-rev-001-20261120T232103Z`. The reviewer recomputed
and matched all three hashes. The live verification record links the exact
preceding inspection and receipt by filename and SHA-256. The preceding
inspection links the exact runner, tests, and R4 report by SHA-256.

| Evidence file | SHA-256 |
|---|---|
| `remote-evidence-20261120T233701Z.json` | `c35d2732f239a55d6c7aed6a3cf832a832ae14e3f6f7fab15b764ed02a7c926f` |
| `smoke-20261120T235639330Z.json` | `734bebe533bfe228493ba7d29bf94e61fe55f8c05173d8e0029d076ca3ce9211` |
| `live-smoke-verification-454a4ff5.json` | `3d5c6da1d235f9201588da3c54e5f12d9e83acb963f0471c457e2e5c700eef7c` |

- **Exact invocation** `vddai.staging_smoke.v2`, run
  `454a4ff56970406fa0f33148deeba56b`, verified recorder exit `0`, verdict
  `PASS`, and prediction `2`. The original state receipt at
  `D:/VDDAI-local/w8d4-staging-smoke/state/smoke-20261120T235639330Z.json`
  has the same SHA-256. The run spans 2026-11-20 23:56:48.156761 UTC through
  23:57:18.973979 UTC. The seven ordered passing stages are `health`,
  `authentication`, `upload_queue`, `ownership`, `inference`,
  `persistence_readback`, and `final_health`.
- **HTTP corroboration** The preserved, timestamped API access window spans
  the exact receipt interval and contains 12 matching rows in client order.
  It shows one anonymous history `401`, two login `200` responses, four
  authorized history `200` responses, one upload `202`, the
  `/predictions/2` and `/predictions/0` `404` responses, and two
  `/predictions/2` `200` responses for the detail reads. The R4 code and
  receipt establish JWT-subject checks, the matching safe `404` response
  bodies, owner-scoped reads, the full frozen result validation, and identity
  preflight and final check. The sanitized access rows corroborate routes,
  statuses, and ordering. The preserved result fingerprint is
  `sha256:65565823ebf2715a7a08647cbb59e064da04f0419561bd029cb534dc84981647`.
- **Persistence and authorization** The post-run PostgreSQL observation at
  Alembic `20260821_04` shows prediction `2` `completed` for owner `2` with
  populated lineage and matching result/lineage package. Both dedicated
  accounts, IDs `2` and `3`, were active non-admins, with prediction counts
  `1` and `0` respectively. Provisioning completed before the invocation and
  its sanitized record includes the protected-file ACL check. Prior
  prediction `1` was still `completed` with its package and lineage present.
- **Local state** The original pending `run.json` matches the exact start
  timestamp, run ID, target, model/package IDs, owner `2` and other account
  `3`. Pending `prediction.json` contains only prediction ID `2`. The
  receipt reports `cleanup_status=pending`. Reconciliation remains a
  separately authorized operator action.
- **Deployment identity** The recorded container observations on both sides
  of the smoke show the same running API and worker container IDs and image
  IDs, each configured with GHCR digest
  `sha256:488b3f7fe19cb91461357e25e24b0cbadb877814568a33cf71aadebabbe67ae5`
  from revision `1b9f6160883361bdb99298b256815197ccab8eba`. The prior
  operational inspection also records the distinct, cached previous GHCR
  digest `sha256:7becd911afdb0bbcd0dc5c2f8b7f261bea151a7a636dd338f25415ce21a503a8`
  from revision `8113c89897c4bc446551f0ec7adf204bae3b8c38`. A source comparison
  shows equal application runtime, ML, Alembic, Dockerfile, and pinned
  dependency paths across these revisions.
- **Registry and backups** The recorded registry SHA-256
  `779626c3da2a05edc8b2407a5c88222fb7c33295ac6cbd8d890b9785573e9c8a`
  matches the earlier authenticated inspection, post-smoke observation, and
  the archived registry member. Both recorded environment pointers select
  `mvtec-tile-resnet18-knn-fe64db2228370b2d-dadb8ca7c9b0` with empty rollback
  pointers. Expected and observed model/package IDs agree at both smoke
  health checks, with result package
  `mvtec-tile-resnet18-knn-fe64db2228370b2d`. The earlier inspection
  recorded a readable logical dump listing whose required table data and
  table of contents agree with the saved listing. The selective archive
  read matches the earlier staging prediction identity/status/package
  fingerprint for the one baseline prediction. These checks support the
  observed staging inputs and retained baseline.

The independent reviewer worked from the preserved, sanitized records and
original receipt/state metadata. Earlier authenticated host inspection,
deployed container and PostgreSQL observations, and recorder exit status
come from the recorded collection. The receipt supplies the result digest
and contract stage outcomes, with request status and persistence corroborated
by their respective summaries.

## Acceptance-criteria coverage

| Criterion | Evidence and current status |
|---|---|
| Health, auth, and owner isolation after deploy | Verified by the live HTTPS receipt, exact R4 client, two active non-admin accounts, and ordered live access rows. |
| Upload, queue, real inference, persistence, and result read | Verified by the sole `202`, live `completed` prediction `2`, owner/other history checks, exact typed result matching, and persisted lineage and package agreement. |
| Verify serving identities and define previous application/model rollback | Current image IDs/digests and health/registry identity verified for the smoke window. Distinct previous application digest and explicit previous model procedure are documented, with the prior model pointer unavailable on the observed registry. |
| Perform and document one application rollback rehearsal | Operator-reported isolated rollback and roll-forward retained. The dated execution record remains open under VDDAI-REV-001. |
| Automated smoke and tested rollback procedure | Automated gate executed successfully on the intended live deployment. Independent proof of the rollback phase sequence is still due. |
| Tests, documentation, and a visible commit | Exact R4 repository verification remains applicable. The guide draft and scoped commit remain at their existing lifecycle gates. |

## Checks run

- `git status --porcelain=v1 --untracked-files=all`, `git branch --show-current`,
  `git rev-parse HEAD`, `git merge-base HEAD master`, and `git diff --cached --stat`
  confirmed the exact branch, common base, and empty index. `Get-FileHash
  -Algorithm SHA256 -LiteralPath` matched the seven repository hashes.
- `Get-FileHash -Algorithm SHA256 -LiteralPath` and pinned Python 3.14.3 via
  `& $vddaiPinned -` independently matched the three sanitized evidence hashes
  and original receipt. Local Python checks parsed the explicit allowlisted
  records for cross-links, schema, exit, ordered stages and timestamps,
  matching pending files, exact API access sequence, database/role observations,
  before/after containers, registry/archive equality, and dump and retained
  event limits. All five assertion groups passed.
- The image source comparison returned no production-path changes. The
  corresponding `git diff --name-status` including tests showed the
  staging-launch test addition.

  ```powershell
  git diff --exit-code 8113c89897c4bc446551f0ec7adf204bae3b8c38 1b9f6160883361bdb99298b256815197ccab8eba -- app ':(exclude)app/tests/**' ml alembic alembic.ini requirements.txt Dockerfile
  ```

- `git diff --check` passed for tracked changes. The documentation validator
  passed before R5 was added with 25 canonical documents and 74 Markdown
  files.

  ```powershell
  $vddaiPinned = 'C:/Users/S.R.G/AppData/Local/Temp/vddai-w8d4-portable-f21215c20b9c4305be685aa56e1b3e31/runtime/python.exe'
  $env:PYTHONDONTWRITEBYTECODE = '1'
  & $vddaiPinned scripts/validate_docs.py
  ```

## Checks outside the independent review run

The earlier authorized live operation supplied the smoke receipt and remote
inspection observations. This re-review used local files and existing
evidence. The implementation hashes are the same as R4, which already
records 105 independent focused tests and the Coder-reported Windows/Linux,
canonical, and strict PostgreSQL runs.

## Ordered handoff

1. Preserve the live receipt and its linked observations as accepted smoke
   evidence for the exact R4 implementation.
2. The environment owner supplies the existing dated application rehearsal
   record for VDDAI-REV-001. Preserve the reported isolated success and use
   the attributable phase evidence for the remaining independent review.
3. Begin QA when the current subject has an eligible review. Documentation
   follows QA `PASS` and owns synchronization of the draft guide with the
   current runner and reconciliation procedure. The combined subject then
   goes to the human decision.
4. Keep the test run pending until the operator's separate reconciliation
   authorization and validated terminal-row/storage procedure are in place.

## Residual risks and assumptions

- The smoke evidence describes the deployment window above. The missing
  lifecycle and phase records leave the rehearsal's exact timing and
  recovery association unresolved.
- The sanitized evidence retains result and lineage identities while the
  full typed response is validated by the exact client on the live
  request. The reviewer cross-checked the retained result digest and
  PostgreSQL package/lineage summary.
- The observed registry has no explicit previous selection. An actual model
  rollback depends on an existing approved target and its separate human
  gate. The application-only rehearsal retains the selected model.
- The protected pending marker continues to block another smoke upload
  until the operator reconciles the current run under separate authority.

## Process-learning evidence

- **Observation** A hash-bound live receipt, API status window, PostgreSQL
  state, and container snapshots established the current automated gate
  while leaving the historic transition evidence independently checkable.
- **Evidence** The three preserved operational records, their cross-links,
  and VDDAI-REV-001 in this report.
- **Impact** The live criterion advanced on verified evidence without
  conflating current successful serving with proof of a rollback phase.
- **Recurrence** Unknown.
- **Candidate improvement** None.
- **Authority note** This evidence carries no authority to change a skill or
  workflow or to approve remediation.
