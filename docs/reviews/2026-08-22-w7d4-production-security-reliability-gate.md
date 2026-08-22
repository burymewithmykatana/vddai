# W7D4 Production Security and Reliability Gate Review

- Review ID: `VDDAI-REVIEW-W7D4-2026-08-22-01`
- Date: 2026-08-22
- Task: Notion `W7D4 — Run the production security and reliability gate`
- Task URL: <https://app.notion.com/p/3ac0ab50ef67816f9fb4d183c3c1054d>
- Branch: `codex/test/w7d4-production-gate`
- Base: `1c5e44001ec76e538b729dec85f007404158b717`
- Head: `e7f8be1fa5aa70817d0aab47e34dd2d79c4e6f28`
- Reviewed range: `1c5e44001ec76e538b729dec85f007404158b717..e7f8be1fa5aa70817d0aab47e34dd2d79c4e6f28`
- Initial working-tree state: clean; ignored local model-registry and runtime artifacts were not part of the Git subject

## Contract sources and acceptance criteria

The review used the Notion task, the human-approved Planner/Coder handoff in
the task conversation, `AGENTS.md`, `app/AGENTS.md`, `ml/AGENTS.md`,
`docs/README.md`, `docs/catalog.yaml`,
`docs/architecture/system-requirements.md`,
`docs/engineering/agent-workflow.md`, and accepted ADRs 0003, 0004, 0005,
0007, 0008, 0009, 0010, and 0011.

The task requires:

1. PostgreSQL migration upgrade, downgrade, and re-upgrade evidence.
2. Coverage for unauthorized access, malformed payloads, corrupt images,
   unavailable dependencies, and cleanup.
3. A remaining-risk register with owners.
4. A green production-style integration suite whose required evidence is
   recorded without silently waiving release-blocking failures.
5. v0.1.0 scope, tests, documentation, and a visible commit.

## Verdict

`CHANGES REQUIRED`

The implementation assembles broad permanent coverage, adds a real PostgreSQL
migration round trip, and records an appropriate risk register. It is not yet a
trustworthy green gate: required PostgreSQL tests can all skip with exit code
zero, the deployed probe's environment denylist can create data in commonly
named production-like environments, and the probe does not bind its completed
result to the package selected by health or independently enforce the frozen
decision rule.

## Findings

### VDDAI-REV-001 — HIGH — Required PostgreSQL checks can skip with a successful gate exit

- Status: `OPEN`
- Location: `app/tests/test_production_gate_postgres.py:13-19`
- Related locations: `app/tests/test_prediction_admission_postgres.py:23-30`,
  `app/tests/test_prediction_worker_postgres.py:23-30`,
  `docs/engineering/production-readiness.md:20-28`, and
  `docs/engineering/production-readiness.md:46-60`

Evidence: all six PostgreSQL tests selected by
`w7_production_gate and postgres_integration` use `skipif` when
`VDDAI_TEST_POSTGRES_DATABASE_URL` is absent. An independent run with the
variable removed reported `6 skipped, 316 deselected` and
`PYTEST_EXIT_CODE=0`. This contradicts the documented rule that a PostgreSQL
skip makes the gate `BLOCKED` and that failures or missing dependencies must
not become green.

Failure scenario: an operator or CI job runs the documented marker command
without provisioning the URL. Pytest exits successfully, and ordinary
pass/fail automation can publish a green W7D4 result even though migration,
concurrency, and fencing behavior never ran on PostgreSQL.

Why it matters: preventing a false-green gate is the core W7D4 outcome. A prose
instruction to inspect skip counts is not an executable release gate.

Required action: add one documented W7D4 entry point or preflight that exits
nonzero when the PostgreSQL URL is missing or when any required PostgreSQL test
skips. Preserve the canonical default suite's optional PostgreSQL behavior if
that remains intentional; the stricter behavior must apply to the production
gate itself.

Closure verification:

- With `VDDAI_TEST_POSTGRES_DATABASE_URL` unset, the documented W7D4 command
  exits nonzero with a clear `BLOCKED` diagnostic.
- With an explicitly disposable PostgreSQL 16 URL, all six PostgreSQL tests
  run and pass with zero skips.
- The ordinary canonical suite retains its intended optional-database behavior.

### VDDAI-REV-002 — HIGH — The data-creating probe accepts production aliases and shared staging environments

- Status: `OPEN`
- Location: `scripts/prove_real_inference.py:147-154`
- Related locations: `app/core/config.py:9`,
  `docs/engineering/production-readiness.md:14-16`, and
  `docs/engineering/production-readiness.md:86`

Evidence: `ENVIRONMENT` is an unconstrained string, while the probe rejects
only the exact case-insensitive value `production`. Independent calls showed
that `prod`, `production-us`, `staging`, and even `" development "` are all
accepted. The probe then creates two users, prediction history, and a retained
input object and intentionally performs no record-coupled cleanup.

Failure scenario: a real deployment identifies itself as `prod`,
`production-us`, or another common non-exact production label, or an operator
runs the command against a shared staging stack. The advertised safety guard
passes and the probe mutates persistent application data.

Why it matters: the root contract forbids unapproved production mutation, and
the W7D4 document restricts this probe to a disposable local or test target.
A denylist over an unconstrained environment value does not fail closed.

Required action: make the probe require an explicit safe environment identity
or equivalent positive opt-in, normalize the value, and reject every other
environment before registration or upload. Keep the check before all mutating
requests and document the exact accepted identities/confirmation mechanism.

Closure verification:

- Unit tests reject `production`, `prod`, `production-us`, `staging`, blank,
  padded, and unknown identities before `_register_and_login` can run.
- Explicitly supported disposable `development`/`test` identities (or an
  approved equivalent confirmation flow) still pass.
- The deployed disposable-stack proof passes and creates no data when the
  preflight rejects its target.

### VDDAI-REV-003 — MEDIUM — Deployed inference evidence is not bound to the selected package or strict decision semantics

- Status: `OPEN`
- Location: `scripts/prove_real_inference.py:207-251`
- Related locations: `scripts/prove_real_inference.py:266-275` and
  `scripts/prove_real_inference.py:341-351`

Evidence: `validate_completed_prediction()` checks that the package ID matches
the embedded lineage but never checks `predicted_label` against
`anomaly_score > threshold`. `prove_real_inference()` obtains the health
selection but discards its package identity and accepts any internally
self-consistent result package. Independent checks demonstrated both false
passes: an `anomalous` result with score `1.0` and threshold `2.0` was accepted,
and a health selection for `package-a` followed by a completed result from
`package-b` returned success.

Failure scenario: deployment drift, stale worker configuration, or a broken
response contract returns a result from a different package or with an
inconsistent label. The command still prints `W7D4 production gate passed`.

Why it matters: the task asks to verify the real selected-package inference
path as one system. Unit contract tests reduce runtime risk but do not make the
black-box deployed proof assert the evidence it claims to prove.

Required action: validate the strict `score > threshold` rule in the probe and
bind the completed package ID to the health-selected package. If promotion
during a probe is supported, define and verify a stable-selection strategy
(for example, read selection before and after and fail on drift) rather than
silently accepting either package.

Closure verification:

- Probe unit tests reject both label/score/threshold contradictions, including
  threshold equality semantics.
- Probe unit tests reject health/result package mismatch and selection drift.
- The disposable deployed proof still passes with one exact selected package
  and reports that package ID.

## Acceptance-criteria coverage

| Criterion | Implementation evidence | Review result |
|---|---|---|
| PostgreSQL upgrade/downgrade/re-upgrade | `app/tests/test_production_gate_postgres.py` creates a UUID schema, checks PostgreSQL 16, preserves representative legacy values, runs `upgrade head`, `downgrade base`, and `upgrade head`, then drops only that schema. | Behavior is present, but the required gate can skip it and still exit zero (`VDDAI-REV-001`). |
| Unauthorized, malformed, corrupt, unavailable dependency, and cleanup coverage | The marker selects authentication/ownership, image validation, storage cleanup, package failure, worker failure, and deployed-probe tests; collection found 143 selected tests. | Broad coverage is present. The deployed probe safety and evidence binding remain defective (`VDDAI-REV-002`, `VDDAI-REV-003`). |
| Remaining risks and owners | `docs/engineering/production-readiness.md` records W7-R01 through W7-R08 with owners and release conditions. | Satisfied for the reviewed scope. Risks remain release conditions rather than silent waivers. |
| Green production-style suite and recorded evidence | README and readiness documentation define commands; the Coder handoff recorded 322 full-suite passes, 143 marked passes with PostgreSQL, six PostgreSQL passes, and a successful deployed real-inference run. | Not satisfied as an enforceable gate because missing required dependencies can return success and the deployed proof has false-pass cases. |
| v0.1.0 scope, tests, docs, visible commit | One focused commit changes tests, the probe, marker configuration, README, and current engineering documentation without runtime architecture changes. | Satisfied. |

## Checks run

- `python -m pytest --collect-only -q -m w7_production_gate` — passed;
  143 of 322 tests selected, 179 deselected.
- With `VDDAI_TEST_POSTGRES_DATABASE_URL` removed,
  `python -m pytest -q -m "w7_production_gate and postgres_integration"` —
  process exit 0 with six skips; this reproduces `VDDAI-REV-001`.
- Inline Python call to `validate_health_checks()` — accepted `prod`,
  `production-us`, `staging`, and padded development values; this reproduces
  `VDDAI-REV-002`.
- Inline Python call to `validate_completed_prediction()` — accepted an
  anomalous label with score below threshold; this reproduces part of
  `VDDAI-REV-003`.
- Inline isolated probe with stubbed HTTP helpers — health selected
  `package-a`, result used `package-b`, and the probe returned success; this
  reproduces the package-binding part of `VDDAI-REV-003`.
- `python -m pytest -q app/tests/test_prove_real_inference.py` — 7 passed.
- `python scripts/validate_docs.py` — passed; 22 canonical documents and 49
  Markdown files.
- `python -m black --check scripts/prove_real_inference.py app/tests/test_prove_real_inference.py app/tests/test_production_gate_postgres.py`
  — passed; three files unchanged.
- `git diff --check 1c5e44001ec76e538b729dec85f007404158b717..e7f8be1fa5aa70817d0aab47e34dd2d79c4e6f28`
  — passed.
- `python scripts/graphify_repository.py validate` — unavailable because the
  local Graphify state did not match the reviewed HEAD; direct source
  inspection was used.

## Checks not run

- The full 322-test canonical gate was not repeated. The Coder supplied a
  successful exact-run result for the reviewed head, while this review focused
  on independently reproducing gate false-positive behavior.
- PostgreSQL-backed tests with a configured database, Docker Compose startup,
  and the deployed data-creating probe were not repeated during review. The
  services were stopped, and the Reviewer write/data boundary does not permit
  mutating the retained local database, image storage, or model registry. The
  Coder supplied successful PostgreSQL 16, container, and deployed-probe
  evidence for this head.
- No model registration, promotion, rollback, artifact regeneration, push,
  merge, or deployment was performed.

## Ordered remediation handoff

1. `VDDAI-REV-001`: make the documented W7D4 entry point fail when required
   PostgreSQL coverage is unavailable or skipped; verify both missing-URL and
   PostgreSQL 16 paths.
2. `VDDAI-REV-002`: replace the probe's production denylist with a fail-closed
   disposable-target preflight and cover production aliases and unknown values.
3. `VDDAI-REV-003`: bind completed inference to the selected package and assert
   strict decision semantics, including equality-normal behavior.
4. Run the focused probe tests, the strict W7D4 gate with PostgreSQL 16, the
   full canonical verification, and the disposable deployed proof.
5. Return the remediation range for independent re-review; preserve all three
   finding IDs in the re-review request.

## Residual risks and assumptions

- W7-R01 through W7-R08 remain the authoritative recorded operational risks;
  this review does not accept or waive them.
- The local ignored registry promotion and probe-created records are
  operational evidence outside the reviewed Git range.
- The review assumes the supplied Coder evidence corresponds to head
  `e7f8be1fa5aa70817d0aab47e34dd2d79c4e6f28`; no later implementation changes
  were present when review began.
- The review report is audit evidence only and does not authorize remediation,
  QA, merge, deployment, or production model changes.
