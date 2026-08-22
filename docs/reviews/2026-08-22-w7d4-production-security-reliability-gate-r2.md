# W7D4 Production Security and Reliability Gate Re-review

- Review ID: `VDDAI-REVIEW-W7D4-2026-08-22-02`
- Date: 2026-08-22
- Task: Notion `W7D4 — Run the production security and reliability gate`
- Task URL: <https://app.notion.com/p/3ac0ab50ef67816f9fb4d183c3c1054d>
- Prior report: `docs/reviews/2026-08-22-w7d4-production-security-reliability-gate.md`
- Branch: `codex/test/w7d4-production-gate`
- Base and merge base: `1c5e44001ec76e538b729dec85f007404158b717`
- Committed head: `e7f8be1fa5aa70817d0aab47e34dd2d79c4e6f28`
- Committed range: `1c5e44001ec76e538b729dec85f007404158b717..e7f8be1fa5aa70817d0aab47e34dd2d79c4e6f28`
- Remediation state: unstaged changes in four tracked files plus two untracked
  implementation files; no staged changes

## Reviewed subject fingerprint

The re-review covers the committed range above plus these exact remediation
files. SHA-256 values allow QA to confirm that an uncommitted subject has not
changed:

| SHA-256 | Path |
|---|---|
| `d8e03cf8b7084f16e3cfac92d710be7328a41fb334d35140dab9de141468b29e` | `app/tests/test_prove_real_inference.py` |
| `02a29d72d9636c7a15e1014877b54525801b206004becdefb72650cf14e75758` | `app/tests/test_run_production_gate.py` |
| `2a637f49c4ec7a6f0903f799e957052357fb375ddbb646dcfb002fb848f1d365` | `docs/engineering/production-readiness.md` |
| `99b1f34beecc226580e2cdc4903178f6f83bae1153d66560e0f1611c37c6019b` | `readme.md` |
| `cbd105c0d17aabb7c28f97c103de22292935b6e2c020352a252ee01b2b9af236` | `scripts/prove_real_inference.py` |
| `c24bf24d6c7b8edc9b03e375ebf09f2e295673f024956be8593714aeed2acbdc` | `scripts/run_production_gate.py` |

The prior review report is immutable audit evidence and is not an
implementation file. The ignored local registry and runtime artifacts are not
part of the Git subject.

## Contract sources and acceptance criteria

The re-review used the Notion task and approved Planner/Coder handoff as
captured by the prior report, `AGENTS.md`, `app/AGENTS.md`, `docs/README.md`,
`docs/catalog.yaml`, `docs/engineering/production-readiness.md`, the executable
contract in `app/contracts/inference.py`, and accepted ADRs 0003, 0004, 0005,
0007, 0008, 0009, 0010, and 0011.

The acceptance criteria remain:

1. PostgreSQL migration upgrade, downgrade, and re-upgrade evidence.
2. Coverage for unauthorized access, malformed payloads, corrupt images,
   unavailable dependencies, and cleanup.
3. A remaining-risk register with owners.
4. A green production-style integration suite whose required evidence is
   recorded without silently waiving release-blocking failures.
5. v0.1.0 scope, tests, documentation, and a visible commit.

## Verdict

`PASS WITH DOCUMENTED RISK`

All three findings from the prior report are verified resolved, and no new
actionable finding was identified. The reviewed implementation is eligible for
independent QA. This verdict does not clear W7-R01 through W7-R08, authorize a
production release, accept a release-condition waiver, approve a model
promotion, or authorize merge.

## Findings

### VDDAI-REV-001 — HIGH — Required PostgreSQL checks can skip with a successful gate exit

- Status: `VERIFIED RESOLVED`
- Location: `scripts/run_production_gate.py:12-99`
- Tests: `app/tests/test_run_production_gate.py:20-100`
- Documentation: `docs/engineering/production-readiness.md:48-68` and
  `readme.md:359-386`

Fresh evidence: the documented entry point checks
`VDDAI_TEST_POSTGRES_DATABASE_URL` before invoking pytest and returns exit 1
with a clear `BLOCKED` diagnostic when it is absent. Its pytest plugin records
every collected test bearing both `w7_production_gate` and
`postgres_integration`, changes a successful session to failure when required
evidence is absent or skipped, and preserves ordinary pytest failures. Unit
tests cover missing configuration, runner arguments, skipped evidence, and no
required PostgreSQL collection. Independent execution reproduced the exit-1
missing-URL path. The Coder's final disposable-PostgreSQL evidence ran all 161
selected W7 tests with zero skips; the independently repeated canonical suite
retained its intended six optional PostgreSQL skips.

Closure result: the production gate can no longer turn the missing-database or
skipped-required-test cases from the original finding into a green result.

### VDDAI-REV-002 — HIGH — The data-creating probe accepts production aliases and shared staging environments

- Status: `VERIFIED RESOLVED`
- Location: `scripts/prove_real_inference.py:149-187` and
  `scripts/prove_real_inference.py:307-344`
- Tests: `app/tests/test_prove_real_inference.py:76-151`
- Documentation: `docs/engineering/production-readiness.md:12-17` and
  `docs/engineering/production-readiness.md:91-91`

Fresh evidence: `validate_health_checks()` now uses a positive allowlist of
case-normalized `development` and `test`, rejects padded identities, and rejects
every other value. `prove_real_inference()` completes all three read-only
health requests and validation before the first registration or upload.
Regression tests reject `production`, `prod`, `production-us`, `staging`,
blank, padded, and unknown identities, and a full control-flow test proves that
registration is unreachable for an unsafe target. The Coder supplied a
successful deployed proof against the disposable development stack after this
change.

Closure result: the original aliases and shared-staging failure scenarios now
fail closed before application data is created.

### VDDAI-REV-003 — MEDIUM — Deployed inference evidence is not bound to the selected package or strict decision semantics

- Status: `VERIFIED RESOLVED`
- Location: `scripts/prove_real_inference.py:190-215`,
  `scripts/prove_real_inference.py:249-304`, and
  `scripts/prove_real_inference.py:403-420`
- Tests: `app/tests/test_prove_real_inference.py:172-247`

Fresh evidence: the probe imports the executable v1
`classify_anomaly_score()` contract and rejects either label contradiction
while preserving equality as normal. It records the initial health selection,
reads model health again after completion, fails on a model-version or package
selection change, and requires the completed result's package ID to match the
stable selected package. Existing result validation also requires persisted
`model_version` to match lineage. Unit tests cover both decision
contradictions, equality, result-package mismatch, selection drift, and stable
success. The documented direct script invocation has a subprocess regression
test. The Coder's deployed proof reported one stable package,
`mvtec-tile-resnet18-knn-fe64db2228370b2d`, with score
`13.027523040771484`, threshold `4.2167956829071045`, and label `anomalous`.

Closure result: the deployed proof now verifies the frozen decision rule and
one exact selected-package inference path rather than accepting internally
self-consistent but unrelated output.

### New findings

No new actionable findings were identified.

## Acceptance-criteria coverage

| Criterion | Implementation and verification evidence | Re-review result |
|---|---|---|
| PostgreSQL upgrade/downgrade/re-upgrade | `app/tests/test_production_gate_postgres.py` exercises PostgreSQL 16 in a UUID schema, preserves representative legacy values, upgrades to head, downgrades to base, and re-upgrades. The strict runner prevents absent or skipped PostgreSQL evidence from being green. Coder evidence: 161 passed with zero skips on disposable PostgreSQL 16. | Satisfied. |
| Unauthorized, malformed, corrupt, unavailable dependency, and cleanup coverage | The marker selects 161 of 340 tests across authentication, ownership, validation, storage cleanup, admission, worker reliability, artifact failure, and deployed-probe behavior. Focused remediation tests passed independently. | Satisfied. |
| Remaining risks and owners | `docs/engineering/production-readiness.md` retains W7-R01 through W7-R08 with owners, severities, release conditions, and operational boundaries. | Satisfied; risks are not waived. |
| Green production-style suite and recorded evidence | The entry point is now fail-closed for required PostgreSQL evidence. Coder evidence records the zero-skip PostgreSQL run and successful disposable deployed inference; independent canonical verification passed. | Satisfied for the reviewed implementation. |
| v0.1.0 scope, tests, docs, visible commit | The committed W7D4 subject remains one focused commit at `e7f8be1`; remediation is limited to the three approved IDs, their tests, and truthful operator documentation. No runtime architecture or public API contract changed. | Satisfied. |

## Checks run during re-review

- With `VDDAI_TEST_POSTGRES_DATABASE_URL` removed,
  `.venv\Scripts\python.exe scripts/run_production_gate.py` — exited 1 with
  `W7D4 production gate BLOCKED` before pytest.
- `.venv\Scripts\python.exe -m pytest -q app/tests/test_run_production_gate.py app/tests/test_prove_real_inference.py`
  — 25 passed in 5.53 seconds.
- `.venv\Scripts\python.exe -m pytest --collect-only -q -m w7_production_gate`
  — 161 of 340 tests collected; 179 deselected.
- `.\scripts\verify.ps1 -IncludeDockerConfig` — passed: Python, pip, exact
  pins, `pip check`, documentation validation, 334 default-suite passes, six
  intentional optional-PostgreSQL skips, and Docker Compose configuration.
- `.venv\Scripts\python.exe -m black --check scripts/prove_real_inference.py scripts/run_production_gate.py app/tests/test_prove_real_inference.py app/tests/test_run_production_gate.py app/tests/test_production_gate_postgres.py`
  — passed; five files unchanged.
- `git diff --check 1c5e44001ec76e538b729dec85f007404158b717..e7f8be1fa5aa70817d0aab47e34dd2d79c4e6f28`
  and `git diff --check` — passed.
- `python scripts/graphify_repository.py validate` — returned unavailable
  because the graph's head commit is stale; direct source and diff inspection
  was used.

## Checks not run during re-review

- The positive strict runner against PostgreSQL 16 was not repeated because
  the Reviewer role does not create and drop external database schemas. The
  Coder's final exact-subject run reported `161 passed, 179 deselected` with
  zero skips in 46.08 seconds.
- Docker services and the deployed probe were not started because the probe
  intentionally creates retained users, prediction history, and an input
  object. The Coder supplied final exact-subject container, log, and package
  evidence. The Reviewer inspected the implementation and independently ran
  its non-mutating regression coverage.
- The repository-wide Black check was not repeated. The Coder recorded the
  known 35-file pre-existing baseline drift; the five Python files in the
  reviewed W7D4 subject pass Black independently.
- No registry registration, model promotion or rollback, artifact generation,
  production operation, push, merge, or commit was performed.

## Ordered handoff

There is no remediation handoff because no finding remains open.

1. Independent QA should verify the exact fingerprinted subject against every
   W7D4 criterion, including the disposable PostgreSQL and deployed-stack
   paths permitted to QA.
2. If QA passes, Documentation should confirm the durable repository guidance
   against the reviewed and QA-verified subject.
3. A human must explicitly authorize any remediation commit, push, merge,
   deployment, production model action, or release-condition acceptance.

## Residual risks and assumptions

- W7-R01 through W7-R08 remain authoritative. In particular, secrets,
  ingress limits, single-host storage, retention, runtime artifacts, rollback,
  probe-created data, and unattended monitoring retain their documented
  release conditions.
- The strict runner proves test availability and results; the operator remains
  responsible for confirming that the supplied PostgreSQL URL identifies a
  disposable non-production database.
- The environment allowlist proves the API's declared identity. It does not
  independently authenticate infrastructure ownership, so target selection
  remains an operator responsibility.
- The remediation is uncommitted. QA must confirm the six SHA-256 values above
  or review a later explicitly authorized commit containing exactly this
  subject.
- This report approves code-review progression only. QA, documentation,
  commit, merge, deployment, and production-model gates remain separate.
