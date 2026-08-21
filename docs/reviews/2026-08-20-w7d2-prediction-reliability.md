# W7D2 Prediction Lifecycle, Retries, and Idempotency Review

- Review ID: `VDDAI-W7D2-REVIEW-2026-08-20-01`
- Date: 2026-08-20
- Task: W7D2 — Harden prediction lifecycle, retries, and idempotency
- Review type: initial implementation review
- Verdict: `CHANGES REQUIRED`
- Base: `e8a1b092d066b43ae46c7da8f66f8191c0e24c6a`
- HEAD: `e8a1b092d066b43ae46c7da8f66f8191c0e24c6a`
- Branch: `codex/feat/w7d2-prediction-reliability`
- Merge base with `master`: `e8a1b092d066b43ae46c7da8f66f8191c0e24c6a`
- Committed range: none; HEAD remains at the approved fresh-master base
- Staged changes: none
- Reviewed subject: the complete unstaged and untracked W7D2 working tree before
  this review report was added

## Contract Sources and Acceptance Criteria

The review used:

- the approved W7D2 task and its seven Definition-of-Done criteria;
- the human-approved Planner/Coder handoff, including the explicit decision that
  repeated API submissions create distinct jobs and execution uses bounded
  at-least-once computation with fenced authoritative persistence;
- root and `app/` `AGENTS.md` instructions;
- `$vddai-review` and the cataloged documentation workflow;
- `docs/architecture/system-requirements.md`;
- accepted ADRs 0003, 0004, 0005, 0008, and 0009;
- the prediction model, worker, storage and inference error types, public schema,
  Alembic history, tests, environment settings, and complete Git delta.

Graphify was not used as evidence. Its validator reported a stale graph because
the recorded HEAD did not match, so all conclusions below come from direct
repository sources and executed behavior.

## Verdict

`CHANGES REQUIRED`

The core design is sound: PostgreSQL row locking prevents simultaneous claims,
claim and settlement use separate transactions, inference holds no database
transaction, expired leases are recoverable, and attempt fencing prevents an
old worker from authoritatively overwriting a replacement attempt. The public
API and frozen inference result contract remain compatible.

However, a persisted due retry can exceed the currently configured maximum
attempt count, which breaks the approved bounded and deterministic retry policy.
A second, lower-severity validation gap permits infinite retry or lease values
to reach runtime timestamp arithmetic. Both findings are open.

## Findings

### VDDAI-W7D2-REV-001 — MEDIUM — Due retries can exceed the configured maximum

- Status: `OPEN`
- Location: `app/workers/prediction_worker.py:196-247`, especially the due-retry
  eligibility query and unconditional `start_processing` call
- Evidence: `_schedule_retry_or_fail_locked` observes `max_attempts` when it
  settles a failure, but `_claim_next_prediction` does not check the persisted
  attempt count before starting a due retry. An independent in-memory execution
  created a due retry with `attempt_count=2`, invoked the claimant with
  `PredictionRetryPolicy(max_attempts=2, ...)`, and produced both
  `claimed_attempt 3` and `persisted_attempt 3`.
- Reproduction condition: a job is scheduled for retry under a larger policy,
  then the configured maximum is reduced before or during a worker restart.
  The next worker starts inference once more even though the persisted count
  already equals its maximum.
- Impact: the declared attempt bound is not an invariant of the state machine.
  The same persisted job can execute more times than the active retry policy
  permits, so retry behavior depends on configuration history rather than the
  current deterministic policy.
- Required action: before incrementing or executing a due retry, terminally
  settle a retry-waiting row whose persisted `attempt_count` is already greater
  than or equal to `max_attempts`. Keep that transition model-owned and
  transactional; do not merely filter the row out, because that would strand
  it in `processing`. Add a regression test that schedules under a larger
  limit, restarts with a smaller limit, performs no additional inference, and
  reaches the existing safe terminal failure contract without incrementing
  beyond the new maximum.
- Closure criteria: the reproduction reaches terminal `failed`, retains the
  safe public failure code, does not invoke storage or inference again, and
  cannot leave the row retry-waiting or active.

### VDDAI-W7D2-REV-002 — LOW — Non-finite retry timing values are accepted

- Status: `OPEN`
- Location: `app/core/config.py:25-27` and
  `app/workers/prediction_worker.py:40-58`
- Evidence: the Pydantic `gt=0` constraint rejects `NaN` but accepts positive
  infinity, while `PredictionRetryPolicy.__post_init__` accepts both non-finite
  values because comparisons with `NaN` do not satisfy `<= 0`. The accepted
  values later reach `datetime.timedelta`, which raises an overflow or value
  error outside the policy-construction boundary.
- Impact: malformed environment configuration does not fail closed at startup.
  An infinite lease can stop the worker while claiming a queued row; an
  infinite or `NaN` retry delay can repeatedly prevent an already claimed row
  from being scheduled after failure or lease expiry until configuration is
  repaired.
- Required action: reject non-finite retry-delay and lease values in both the
  settings contract and `PredictionRetryPolicy` construction. Keep direct
  policy injection deterministic and validate `max_attempts` as an actual
  positive integer. Add focused `NaN`, positive-infinity, and non-integer
  policy tests.
- Closure criteria: every invalid value fails during settings or policy
  construction, before a row can be locked, claimed, or mutated.

## Acceptance-Criteria Coverage

| Criterion | Review evidence | Status |
|---|---|---|
| 1. Define idempotency for creation and execution | Repeated POSTs intentionally create distinct jobs; row locks plus attempt-token fencing define execution replay behavior | Satisfied |
| 2. Prevent double processing and invalid transitions | PostgreSQL `FOR UPDATE SKIP LOCKED`, committed claims, leases, model transitions, and fencing prevent simultaneous authoritative settlement | Satisfied |
| 3. Define and test retryable versus terminal failures | Generic storage/commit/lease failures retry; missing/invalid inputs, preprocessing, model resolution/package, lifecycle, and unknown failures terminate; the active maximum is not enforced at due claim | Partially satisfied — REV-001 |
| 4. Demonstrate restart recovery | Interruption during inference and after inference-before-settlement is recovered through lease expiry and fenced replacement work | Satisfied |
| 5. Deterministic tested state machine and retry policy | Lifecycle and race tests are substantial, but policy-history-dependent overrun and non-finite timing inputs remain | Not satisfied — REV-001, REV-002 |
| 6. Remain inside v0.1.0 MVP | Existing PostgreSQL queue and worker architecture are retained; no new queue, lock, or orchestration service is introduced | Satisfied |
| 7. Tests and maintained documentation | Implementation tests are present and passing; maintained lifecycle/operations docs and an accepted durable decision remain intentionally pending the post-QA Documentation gate | Pending downstream Documentation gate |

## Checks Run

- `git status --short`, branch/HEAD/merge-base inspection, `git diff --stat`,
  `git diff --check`, and direct reads of every tracked and untracked changed
  file
  - Confirmed the exact review range; `git diff --check` passed with only the
    `.env.example` LF-to-CRLF working-copy warning.
- `python scripts/graphify_repository.py validate`
  - Exited `1`: graph stale because `head_commit` did not match. Direct-source
    inspection was used instead.
- `python -m alembic heads`
  - Passed: `20260820_03 (head)`.
- `python -m black --check` for all nine changed Python files
  - Passed: all files would be left unchanged.
- `docker compose -f docker-compose.yaml config --quiet`
  - Passed.
- `./scripts/verify.ps1`
  - Passed in the pinned environment: exact dependency pins, `pip check`, and
    documentation validation passed; pytest reported `287 passed, 2 skipped`.
- Independent in-memory SQLAlchemy claimant reproduction for
  `VDDAI-W7D2-REV-001`
  - A due retry at count 2 was claimed and persisted as attempt 3 under a
    maximum of 2.
- Direct settings validation probe for `VDDAI-W7D2-REV-002`
  - `NaN` was rejected by settings, but positive infinity was accepted.

## Checks Not Run

- The optional PostgreSQL integration marker was not independently rerun because
  no Compose services were running during review. The Coder evidence was
  inspected and records `2 passed` against PostgreSQL for concurrent
  `SKIP LOCKED` claim behavior and stale-worker fencing.
- The isolated PostgreSQL migration upgrade/downgrade was not independently
  repeated. The Coder evidence records upgrade from `20260803_02`, preserved
  data/defaults, targeted downgrade, and re-upgrade; the automated SQLite
  migration test passed in the independent complete suite.
- Full-repository Black was not repeated. The Coder reported known unrelated
  baseline drift while the changed-file formatting check passes.
- No commit, staging, push, PR, merge, deployment, production, secret, data,
  volume-deletion, or model-promotion action was performed.

## Ordered Remediation Handoff

1. Resolve `VDDAI-W7D2-REV-001` first by adding a model-owned terminal
   transition for an exhausted retry-waiting row and enforcing it under the
   claim row lock before another attempt is started.
2. Resolve `VDDAI-W7D2-REV-002` by making settings and direct retry-policy
   construction reject all non-finite timing values and non-integer maximums.
3. Add the focused regression cases described by each finding, run the pinned
   focused tests and complete verification gate, and preserve this report.
4. Request an independent re-review of the complete remediated working tree;
   do not mark either finding resolved in implementation code or by editing
   this immutable report.

## Residual Risks and Assumptions

- Fixed-duration leases intentionally permit duplicate computation when a live
  inference exceeds its lease. Attempt fencing makes only one current attempt
  authoritative; operators must configure the lease above expected inference
  time. This is an accepted at-least-once-computation tradeoff, not a finding.
- Retry diagnostics are stored only on the current prediction row, not as an
  append-only attempt history. That is within the approved MVP boundary.
- Maintained documentation currently still states that retry/lease orchestration
  is outside the platform boundary. The approved workflow assigns that
  synchronization to Documentation after a passing re-review and QA gate; the
  task is not merge-ready until that pass completes.
- The review report itself is uncommitted audit evidence and was not part of the
  implementation subject evaluated above.
