# W8D4 operational evidence re-review R6

- **Review ID** `W8D4-REV-2026-11-26-006`
- **Date** 2026-11-26
- **Role** Independent VDDAI Reviewer
- **Task** W8D4 — Add deployment smoke test and rollback
- **Branch** `codex/w8d4-smoke-rollback`
- **Base, HEAD, and merge base** `1b9f6160883361bdb99298b256815197ccab8eba`
- **Prior current review** [R5](2026-11-21-w8d4-staging-smoke-r5.md)
- **Review subject** The exact R4 smoke runner and tests, the verified live
  smoke evidence carried forward from R5, and the newly supplied isolated
  rehearsal and cleanup records. The index is empty. The operator guide
  remains the pre-existing draft for the downstream Documentation gate.
  The local artifact tarball is outside the review subject.

| Repository file | Reviewed SHA-256 |
|---|---|
| `scripts/smoke_staging.py` | `6bbf359e0ba4898b4212e3a5ee2eafb9cf42726783638b3df2bcc9b14250dbe3` |
| `app/tests/test_smoke_staging.py` | `3b9153c91b08c5df5a296086394ace1f6848a8c68052acb7ceecb3daececcad5` |
| `docs/engineering/production-readiness.md` draft | `cb691826e3c57181d7057cc29ab01d4ba0c6d11136b37fc9e766bac9d1bd0d3e` |
| R5 | `daa93daddc508c2867edb7f4cc27b1dcb65f60bed7f5de43a44f65320269c6b5` |
| R4 | `1e7e67db11f6b4ea11f318caa5d68e67e1640c85a35a5899d4d2d1231ca22559` |
| R3 | `17902699595704ab3884d807947ada1eb2bca2c6bd7ba27b37030541703abbe4` |
| R2 | `94237aa60d7d1602bf24ad8109a1d20b87066ac154c9dd1e1dc6426f83e75190` |
| Initial review | `7bfe6ffac60adcac2651c59a3fd4b08a016e64bf7deb4e111863b9c61b271df3` |

## Contract sources and acceptance criteria

The task body requires post-deploy health, authentication, upload, queue,
inference, persistence, and result-read checks. It also calls for definitions
of rollback to previous application and model versions, one performed and
documented rehearsal, tests, documentation, and a visible commit. The user
approved one isolated application rollback and roll-forward on
`vddai-server` with stable model selection. The task summary describes the
deferred release gate. The approved rehearsal scope governs this evidence.
A model transition requires its own approval and an explicit registry
rollback target. [W8D4 task](https://app.notion.com/p/3ac0ab50ef678177a31ed823994298a9).
[R5 closure criterion](2026-11-21-w8d4-staging-smoke-r5.md#findings).

The reviewed contracts cover the repository lifecycle, frozen inference and
prediction persistence, the registry and artifact selection, worker recovery
and admission, and digest-pinned staging. [Root instructions](../../AGENTS.md).
[Application instructions](../../app/AGENTS.md).
[Documentation index](../README.md). [Catalog](../catalog.yaml).
[Agent workflow](../engineering/agent-workflow.md).
[Operator-guide draft](../engineering/production-readiness.md).
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

**PASS. The exact reviewed subject is eligible for independent QA.** The
2026-11-26 records close VDDAI-REV-001, including the dated rehearsal phases
and recovery of accepted queued work. R5 supplies the prior independently
verified live HTTPS smoke. Documentation follows eligible QA evidence and
the combined subject remains subject to the human decision.

## Findings

| Finding | Severity | Status | Closure |
|---|---|---|---|
| VDDAI-REV-001 — Deployment smoke and rollback rehearsal evidence | HIGH | VERIFIED RESOLVED | R5 verified live HTTPS smoke. The new isolated rehearsal proves the transition to the exact previous image, recovery of the same queued job, owner read continuity, roll-forward, and scoped cleanup. The dated evidence closes the gap in R5. See the phase and provenance checks below. |
| VDDAI-REV-002 — Pending-reservation durability | MEDIUM | VERIFIED RESOLVED | R4 bound the local filesystem success, failure, and restart checks to the same runner/test hashes. R5 independently verified the live pending marker and saved prediction ID. |
| VDDAI-REV-003 — Catchable cancellation evidence | MEDIUM | VERIFIED RESOLVED | R4's focused regression and real-child checks remain current for the same supervisor bytes. The interruption in the separate operational probe is documented below. |
| VDDAI-REV-004 — Type-exact owner-history readback | MEDIUM | VERIFIED RESOLVED | R4's matching and mismatch regression checks and R5's successful persistence-readback stage remain current for this subject. |

This review found no actionable defect. Prior reports are retained as
recorded. [R4](2026-11-21-w8d4-staging-smoke-r4.md).
[R3](2026-11-21-w8d4-staging-smoke-r3.md).
[R2](2026-08-31-w8d4-staging-smoke-r2.md).
[Initial review](2026-08-31-w8d4-staging-smoke.md).

## Operational evidence and provenance

The 2026-11-26 evidence is retained outside Git at
`D:/VDDAI-local/evidence/w8d4-rev-001/vddai-w8d4-rh-20261126144150z`. Review
recomputed the manifest SHA-256 and all six file SHA-256 values referenced
by it. Separate authority records were fingerprinted independently of the
execution manifest.

| File | SHA-256 |
|---|---|
| `rehearsal-report.json` | `841d2f6d9672f5e3dafc119fbaa532f3581c021182c879ec7b5ac2e3a91653fc` |
| `execution-resumed.json` | `1294636eb71075408182d8e1dd2a4552a7ca27599bd09baf0ee9ef80262443da` |
| `execution-baseline-interrupted.json` | `d844a4921ded8eecfdf943394ad138cf59cc41ff2bb876cffbb0539fb08679ab` |
| `cleanup.json` | `86b20fd5293c69d99e3d54fa2f9d0b39d1e5eaaa2ebfcc225d8fef4f3e7cc08a` |
| `preflight.json` | `51340f7b2c27e829cbfc03bc14bb1b8014748f4944ace40528d264cb95931260` |
| `driver.py` | `f66017e6b3fe81cf5f0aebbfe6610c34ee6cd2140075e5b899d25fca385bbde4` |
| `continuation.py` | `9c71bf0a9bcf2ce27af2819a36d3a9bd9ff5cc385d06eaca91690a4d9d292b19` |
| `acceptance-source.json` | `0d523d9463d9202e1ae274cf7f69574b55e4c7bdac2f73d9496638addf114036` |
| `originating-handoff.json` | `5852e8a5785f84bf03cacf722150f8cc1e553397b2396c68c3be712c30b575fe` |

### One isolated rehearsal

All execution and cleanup records identify `vddai-w8d4-rh-20261126144150z`.
The underlying host identifies itself as `vddai-machine`. The preflight binds
the run to R5 by path and SHA-256. The resumed report carries the original
driver and interrupted execution hashes, the original baseline receipt, and
the original command ledger as its prefix. The cleanup record binds the
exact resumed execution hash and the same continuation script.

The initial baseline probe failed at 14:46:48 UTC with an `AttributeError`.
Its function name shadowed the imported HTTP module. The probe itself
recorded zero requests. The startup process had already issued a read-only
readiness check. The continuation directly imports `HTTPConnection`,
preserves the same API startup command, and rechecks the original container
IDs, labelled internal network and volume, restored single-row database,
and archive/model hashes. The continuation preflight also checked for the
absence of earlier synthetic accounts. It resumed in the same resources
at 14:48:43 UTC and completed the one approved rehearsal.

### Phase and result binding

The isolated probes used loopback HTTP against the exact application images.
All times below are UTC on 2026-11-26. Prediction IDs in this table refer to
the isolated database.

| Phase | Time | Independently checked evidence |
|---|---|---|
| Restore | 14:46:12–14:46:18 | The fresh PostgreSQL volume contains restored historical completed prediction `1`, its upload, schema head `20260821_04`, and the archived model selection. |
| Current baseline | 14:48:45–14:48:51 | The current API and worker completed fresh prediction `2` for the dedicated owner. Detail/history agreed and its result fingerprint was retained. |
| Controlled failure | 14:48:51–14:49:19 | The current worker stopped while the current API stayed healthy. One submission returned `202` for prediction `3`. The bounded probe observed it remaining queued for five seconds. PostgreSQL recorded zero attempts, no start or terminal timestamp, and no processing rows. |
| Rollback | 14:49:19–14:49:50 | The current API stopped. The previous API started and validated health with both workers stopped. Prediction `3` was still the same queued row with the same owner, creation time and uploaded-image SHA-256. The previous worker then started. |
| Recovery | 14:49:50–14:50:02 | Prediction `3` progressed through queued, processing and completed. Its first processing timestamp followed the previous worker startup. PostgreSQL recorded attempt `1`, a released lease, the same upload SHA-256 and matching owner result/lineage. The original owner read back baseline `2`, and fresh prediction `4` completed on the previous image. |
| Roll-forward | 14:50:02–14:50:56 | The previous worker and API stopped before the current API and worker restarted. The original owner readbacks for `2`, `3` and `4` matched their respective earlier result fingerprints. Fresh prediction `5` completed on the current image. PostgreSQL then recorded five completed rows with the original archived row unchanged. |

The command ledger and container snapshots agree on the start/stop order.
At each switch the API started with the opposite worker stopped. The same
PostgreSQL container and volume persisted through both transitions. All four
new completed results match their PostgreSQL projections, share the frozen
lineage fingerprint and package identity, and satisfy the strict score versus
threshold rule. The probe evidence records the matching cross-owner and
missing `404` responses and empty second-account histories.

### Image, archive, and schema safeguards

| Role | Observed digest and source |
|---|---|
| Current API and worker | `sha256:488b3f7fe19cb91461357e25e24b0cbadb877814568a33cf71aadebabbe67ae5` from `1b9f6160883361bdb99298b256815197ccab8eba` |
| Previous API and worker | `sha256:7becd911afdb0bbcd0dc5c2f8b7f261bea151a7a636dd338f25415ce21a503a8` from `8113c89897c4bc446551f0ec7adf204bae3b8c38` |
| PostgreSQL | `sha256:3950ad7c3148ca2175ef1b6c36c9efbf78957ae8fbe8b3a5d7c35af50500382f`, running PostgreSQL 16.16 |

The initial formatted image checks in `preflight.json` produced no
observations and returned exit `1`. Its separate image identity records,
successful execution preflight inspections, and actual container IDs
corroborate the three exact digest references. The run used cached images,
an internal labelled network, a dedicated labelled PostgreSQL volume, and
containers without host port publishing or application code bind mounts.
Application containers shared the isolated copied upload directory and
read-only artifact tree.

The source dump, upload archive, and model archive byte sizes and SHA-256
values agree between read-only preflight and the execution record. The
driver checked the dump stream checksum, listed it and restored into the
verified empty isolated database with `pg_restore --exit-on-error`.
Archive extraction was scoped to the isolated tree. The restore has one
archived upload and 16 artifact files. R6 independently recomputed the
retained archived prediction identity/status/package projection from the
recorded values. It agrees with the restore and the archived row remained
stable across the database snapshots. Each switch observed Alembic
`20260821_04` and the startup command checks migration heads before the
normal upgrade step.

The archived, live and isolated registry SHA-256 values agree. SQLite
integrity, the package manifest and ResNet checkpoint hashes, and the
16-file artifact inventory were recorded before and after. The registry
and phase health selected the same model version and package throughout.
Both observed environment rollback pointers are null, so a future model
transition needs the separately approved explicit previous selection.
The older Windows backup remains historical local evidence. The rehearsal
records the on-host source archives and their use, with off-host retention
and original capture timing outside the verified evidence.

### Cleanup and live invariants

At 14:51:38–14:52:03 UTC the cleanup ledger removed exactly the five
rehearsal container IDs, the matching labelled network and volume, and the
owned temporary working tree. The isolated resource absence checks passed.
Comparison of the recorded live snapshots before execution, after
execution, and on both sides of cleanup confirms the same five live
container identities, image IDs, start times, restart counts and registry
SHA-256. Source backups were verified unchanged. The recorded read-only
live HTTPS checks after cleanup at 14:52:31 UTC returned `200` for service,
database, and the expected selected model/package.

The live authenticated smoke criterion comes from R5's independent
verification of the 2026-11-20 schema-v2 receipt, request access window,
database and lineage observations and before/after deployment identity.
The original live receipt path and its evidence folder were unavailable
in this Windows session. R6 checked R5's immutable hash and carried that
verification forward. The last verified live-smoke test-data reconciliation
status is pending under its separate operator boundary.

## Acceptance-criteria coverage

| Criterion | Evidence and status |
|---|---|
| Post-deploy health, authentication and ownership, upload, queue, inference, persistence and result reads | Verified in R5 against the exact R4 runner. R6 confirmed the reviewed bytes and R5 fingerprint. |
| Define rollback to previous application and model versions | The guide contains explicit compatible application-digest transition and audited model rollback definitions. The completed exercise verified the application procedure with one stable registry selection. Documentation owns guide synchronization after QA. |
| Perform and document one application rehearsal | Verified in R6 with sealed timestamps, the two observed application digests, same-job recovery, retained owner reads, backup and schema checks, and scoped cleanup. |
| Automated smoke and tested rollback procedure | R4 regression evidence, R5 successful live gate, and the R6 isolated execution satisfy this review entry criterion. |
| Tests, documentation, and visible commit | R4's exact-hash verification remains current. Final Documentation and the scoped commit are downstream under the established lifecycle. |

## Checks run

- `git status --porcelain=v1 --untracked-files=all`, `git branch --show-current`,
  `git rev-parse HEAD`, `git merge-base HEAD master`, and `git diff --cached --stat`
  established the exact subject and empty index.
- `Get-FileHash -Algorithm SHA256 -LiteralPath` and pinned Python 3.14.3 via
  `& $vddaiPinned -` recomputed repository and evidence fingerprints. Five local
  assertion groups passed for the sealed manifest and original execution
  binding, dated phase and container ordering, archive/registry/schema
  safeguards, same-job recovery and owner continuity, and cleanup/live checks.
  Read the two outside-repository drivers as source to inspect their controls
  and compared the embedded probe definitions without executing the drivers.
- `Test-Path -LiteralPath` returned false for the R5 source evidence folder
  and original live receipt in this session.
- `git diff --check` passed. The documentation validator passed before adding
  R6 with 25 canonical documents and 75 Markdown files.

  ```powershell
  $vddaiPinned = 'C:/Users/S.R.G/AppData/Local/Temp/vddai-w8d4-portable-f21215c20b9c4305be685aa56e1b3e31/runtime/python.exe'
  $env:PYTHONDONTWRITEBYTECODE = '1'
  & $vddaiPinned --version
  & $vddaiPinned scripts/validate_docs.py
  ```

## Checks outside the independent review run

This re-review used the preserved host records and raw local report files.
The recorded run supplies the actual container, database, worker, archive
and health observations. Local checks establish their cross-file bindings,
hashes, timestamps, consistency and scope. Production-equivalent code gates
remain exact-hash verified in R4, which records 105 independent focused tests
and the Coder-reported Linux, full and strict PostgreSQL checks. R5 retains
the earlier independent live smoke verification.

## Ordered handoff

1. The exact reviewed subject may enter independent QA with this report,
   the R4 and R5 evidence and the sealed rehearsal package.
2. After QA passes, route the draft guide to Documentation to synchronize the
   current invocation, dedicated accounts, pending-state reconciliation, and
   scoped rehearsal guidance. The combined subject then goes to the human
   decision under the maintained workflow.
3. Retain the separate operator boundaries for live test-data cleanup and
   any explicit model transition.

## Residual risks and assumptions

- Operational observations cover the dated windows in their records. R6's
  isolated rehearsal scope is application rollback using the copied state
  and pinned images with stable model selection.
- The first probe interruption is preserved with its exact hash and bounded
  effect. The tested continuation rechecked the same isolated state before
  proceeding.
- The source backups were already on the rehearsal host. Their preserved
  hashes and successful restore establish the rehearsal inputs and leave
  off-host retention and original capture ordering unverified.

## Process-learning evidence

- **Observation** Preserving the interrupted probe receipt and the reused
  resource identities made it possible to verify one continuous rehearsal
  across a probe correction.
- **Evidence** `execution-baseline-interrupted.json`,
  `execution-resumed.json`, `cleanup.json`, and VDDAI-REV-001.
- **Impact** The phase record binds the same accepted job and retained result
  to both image transitions and distinguishes the correction from the
  controlled worker outage.
- **Recurrence** Unknown.
- **Candidate improvement** None.
- **Authority note** This evidence carries no authority to change a skill or
  workflow or to approve remediation.
