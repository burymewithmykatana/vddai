# W7D2 Prediction Lifecycle, Retries, and Idempotency Re-review

- Review ID: `VDDAI-W7D2-REVIEW-2026-08-21-02`
- Date: 2026-08-21
- Task: W7D2 — Harden prediction lifecycle, retries, and idempotency
- Review type: remediation re-review
- Prior report:
  [`2026-08-20-w7d2-prediction-reliability.md`](2026-08-20-w7d2-prediction-reliability.md)
- Verdict: `PASS`
- Base: `e8a1b092d066b43ae46c7da8f66f8191c0e24c6a`
- HEAD: `e8a1b092d066b43ae46c7da8f66f8191c0e24c6a`
- Branch: `codex/feat/w7d2-prediction-reliability`
- Merge base with `master`: `e8a1b092d066b43ae46c7da8f66f8191c0e24c6a`
- Committed range: none; HEAD remains at the approved fresh-master base
- Staged changes: none
- Reviewed subject: the complete unstaged and untracked remediated W7D2 working
  tree and immutable initial report before this re-review report was added

## Contract Sources and Acceptance Criteria

The re-review used:

- the approved W7D2 task and seven Definition-of-Done criteria;
- the human-approved Planner/Coder handoff and approved remediation of both
  original findings;
- the immutable initial review report and preserved finding IDs;
- root and `app/` `AGENTS.md` instructions;
- `$vddai-review` and the cataloged agent workflow;
- `docs/architecture/system-requirements.md`;
- accepted ADRs 0003, 0004, 0005, 0008, and 0009;
- the complete current implementation, migration, configuration, test, and Git
  working-tree state.

Graphify was not used as evidence. Validation reported a stale graph because
the recorded `head_commit` did not match, so all behavioral conclusions were
verified directly from repository source and fresh execution.

## Verdict

`PASS`

Both original findings are verified resolved on the complete remediated
subject. No new actionable findings were identified. The implementation now
enforces the configured attempt bound for already waiting retries, rejects
invalid policies before queue mutation, and preserves the approved locking,
fencing, recovery, API, persistence, security, and inference contracts.

## Findings

### VDDAI-W7D2-REV-001 — MEDIUM — Due retries can exceed the configured maximum

- Status: `VERIFIED RESOLVED`
- Location: `app/models/prediction.py:283-309`,
  `app/workers/prediction_worker.py:211-284`, and
  `app/tests/test_prediction_worker_reliability.py:281-327`
- Fresh evidence: the worker selects the due retry under
  `FOR UPDATE SKIP LOCKED`, checks the persisted count before
  `start_processing`, and calls the model-owned `fail_retry_waiting` transition
  when the count meets or exceeds the active maximum. The transition validates
  retry-waiting shape and the attempt token, clears result and retry metadata,
  preserves the attempt count, and atomically persists terminal failure.
- Executed closure behavior: the original reproduction with a due row at count
  2 and `max_attempts=2` returned no claim and persisted `failed`, count 2,
  `inference_failed`, and `next_attempt_at=None`. The focused restart-policy
  regression also confirms storage is read only for the original failed
  attempt and inference is never invoked after the maximum is reduced.
- Closure conclusion: configuration history can no longer cause an extra
  attempt, and an exhausted waiting row is terminal rather than stranded.

### VDDAI-W7D2-REV-002 — LOW — Non-finite retry timing values are accepted

- Status: `VERIFIED RESOLVED`
- Location: `app/core/config.py:25-35`,
  `app/workers/prediction_worker.py:41-73`, and
  `app/tests/test_prediction_worker_reliability.py:605-657`
- Fresh evidence: settings now use `allow_inf_nan=False` for retry delay and
  attempt lease. Direct policy construction requires a real positive integer
  maximum and finite positive numeric timing values before timestamp
  arithmetic is available.
- Executed closure behavior: focused tests reject fractional maximum, zero,
  `NaN`, and positive infinity inputs. An independent settings probe rejected
  `WORKER_MAX_ATTEMPTS=1.5` and non-finite values for both timing fields.
- Closure conclusion: invalid policy values fail during configuration or policy
  construction before a row can be selected or mutated.

No new actionable findings were identified.

## Acceptance-Criteria Coverage

| Criterion | Re-review evidence | Status |
|---|---|---|
| 1. Define idempotency for creation and execution | Repeated API submissions create distinct jobs; attempt fencing defines replay-safe authoritative settlement | Satisfied |
| 2. Prevent double processing and invalid transitions | PostgreSQL locking, committed claims, explicit model transitions, leases, and attempt tokens prevent concurrent authoritative processing | Satisfied |
| 3. Define and test retryable versus terminal failures | Retry classes, terminal classes, bounded exhaustion, reduced-policy exhaustion, and persistence failures have deterministic coverage | Satisfied |
| 4. Demonstrate restart recovery | Interruption during inference and before settlement is recovered after lease expiry; stale workers are fenced | Satisfied |
| 5. Deterministic tested state machine and retry policy | The active maximum is enforced before retry claim and invalid policies fail before mutation | Satisfied |
| 6. Remain inside v0.1.0 MVP | The existing PostgreSQL queue and worker architecture remain; no new infrastructure or public API redesign was introduced | Satisfied |
| 7. Tests and maintained documentation | Implementation and regression tests pass; durable lifecycle and operator documentation remains assigned to the post-QA Documentation gate | Satisfied at Reviewer gate; Documentation pending |

## Checks Run

- Complete Git status, HEAD, branch, merge-base, staged/unstaged/untracked range,
  initial-report hash, direct implementation source, tests, migrations, and
  governing contract inspection
  - Confirmed the exact remediated subject and that the initial report remains
    unchanged at SHA-256
    `C62BD63BC5E3FAF85591E54DC89C16C8F75B16035581020CD86BBF894D63F575`.
- `python scripts/graphify_repository.py validate`
  - Exited `1`: graph stale because `head_commit` did not match; direct source
    was used instead.
- `python -m pytest -q app/tests/test_prediction_worker_reliability.py -k
  "lowered_retry_limit or settings_reject_non_finite or
  retry_policy_rejects_invalid"`
  - Passed: `13 passed, 10 deselected`.
- Independent in-memory SQLAlchemy execution of the original
  `VDDAI-W7D2-REV-001` reproduction
  - Persisted terminal `failed` at count 2 with no claim and no next attempt
    under `max_attempts=2`.
- Independent settings probes for fractional maximum, `NaN`, and positive
  infinity timing inputs
  - All values were rejected during `Settings` construction.
- `./scripts/verify.ps1`
  - Passed in the pinned environment: exact dependencies, `pip check`, and
    documentation validation passed; pytest reported `297 passed, 2 skipped`.
- `python -m black --check` for all nine changed Python files
  - Passed: all files would be left unchanged.
- `docker compose -f docker-compose.yaml config --quiet`
  - Passed.
- `python -m alembic heads`
  - Passed: `20260820_03 (head)`.
- `git diff --check`
  - Passed with only the `.env.example` LF-to-CRLF working-copy warning.

## Checks Not Run

- The optional PostgreSQL integration marker was not independently rerun in
  this review-only pass because it creates and drops temporary schemas. The
  current Coder remediation evidence records `2 passed` against PostgreSQL and
  restoration of the service to its prior stopped state; the remediation does
  not change SQL selection or locking semantics.
- The isolated PostgreSQL migration upgrade/downgrade was not repeated because
  remediation does not change the migration. Initial Coder evidence records the
  PostgreSQL cycle, and the automated migration regression passed in the
  complete re-review suite.
- Full-repository Black was not run because the repository has documented
  unrelated baseline drift. Every changed Python file passed formatting.
- Docker images were not rebuilt because Compose and dependency behavior did
  not change.
- No commit, staging, push, PR, merge, deployment, production, secret, data,
  volume-deletion, or model-promotion action was performed.

## Ordered Remediation Handoff

There are no open findings and no further Coder remediation handoff. Under the
maintained workflow, the unchanged re-reviewed subject is eligible for
independent QA. This report does not authorize merge or another protected
action.

## Residual Risks and Assumptions

- Fixed-duration leases intentionally permit duplicate computation if a live
  inference exceeds its lease. Attempt fencing permits only the current attempt
  to persist authoritatively; operators must configure the lease above expected
  inference duration. This is the approved at-least-once-computation tradeoff.
- Retry diagnostics remain current-row metadata rather than an append-only
  attempt ledger, within the approved MVP boundary.
- Maintained architecture and operator documentation still predates the new
  retry/lease contract. The approved workflow assigns synchronization to
  Documentation only after QA `PASS`; the task is not merge-ready until that
  gate completes.
- Both review reports remain uncommitted immutable audit evidence.
