# W9D5 local pilot soak review

## 1. Reviewed subject

Review `W9D5-REV-2026-11-28-001`, 28 November 2026. Independent review of
`codex/w9d5-local-pilot-soak` in the W9D5 standalone checkout. The approved
parent and `HEAD` are `8f21330084c9a605c5e0e661b6c7f7c21d68a4cc`, with
`origin/master` merge base `1b9f6160883361bdb99298b256815197ccab8eba`.
The task committed range and index are empty. The two untracked files form
the exact implementation range after Coder reconciled two generated test
directories outside the source tree. Review evidence is separate.

| Reviewed file | SHA-256 |
| --- | --- |
| `scripts/run_local_pilot_soak.py` | `89c274412aa03a750d20b8319170cbb54f18e3122eaccd4d8f06278efafa4c21` |
| `app/tests/test_local_pilot_soak.py` | `0a02b4bc57e7015b5a6c09842872e9004b1bc14c37c1180a4a152fe552a473d1` |

## 2. Contract and acceptance criteria

The [W9D5 task](https://app.notion.com/p/3ac0ab50ef678166b189eacf3ada6840)
requires a measured workload, an evidenced pilot envelope, and resolution
or explicit deferral of its largest bottleneck. It identifies the staging
soak as a deferred server-dependent release gate on an immutable candidate.
The approved local task uses a disposable development target, two synthetic
owners, JPEG/PNG/WebP, a five-minute ten-job warmup, and a fifteen-minute
sixty-job steady phase. Targets are API p95 at most one second, client
submission to observed terminal p95 at most fifteen seconds, inference
p95 at most five seconds, unexpected failures at most one percent, and a
fifteen-second hard per-job deadline. The Compose proof separately samples
queue and resource use. Local completion, the staging release gate, and
production deployment have distinct evidence and authorization.

The [repository rules](../../AGENTS.md), [application rules](../../app/AGENTS.md),
and [agent workflow](../engineering/agent-workflow.md) govern the review.
[ADR 0010](../decisions/0010-database-backed-prediction-reliability.md)
requires a distinct persisted prediction for each accepted upload. The
[private metrics decision](../decisions/0015-private-observability.md) and
[service metrics targets](../engineering/production-readiness.md#w9d2-service-and-queue-metrics)
remain in force.

## 3. Verdict

**CHANGES REQUIRED.** The focused checks passed. Independent probes found a
false passing workload receipt with reused IDs, an overrun of the hard
deadline, and an unhandled type error in the safe failure-report path.
The original measured local workload was active when the report was sealed.

## 4. Findings

### `VDDAI-REV-001` Reused queue receipt IDs can produce a passing workload

**HIGH - OPEN.** `scripts/run_local_pilot_soak.py` lines 193-239,
`docs/decisions/0010-database-backed-prediction-reliability.md` lines 22-26.

The runner checks that each HTTP 202 response has a positive integer ID
and that its subsequent terminal response matches that ID and the selected
package. It does not establish that the upload accepted a distinct new
prediction. Reusing a previously completed result for the same owner
therefore passes the current identity comparison. This can turn result
readback latency into a passing 70-job soak without the claimed workload.

In an independent clock-controlled invocation of the real CLI main
function, all 70 synthetic submissions returned one recycled ID per owner.
Each owner read supplied its matching valid-looking terminal result.
The receipt reported 70 completions and `result: passed` with only two
distinct row IDs.

Require a valid queued acknowledgement and an ID unused by any prior
accepted upload in the run before recording that submission as accepted.
Confirm that same-ID reuse for the same owner is rejected before another
result is counted, that a non-queued acknowledgement is rejected, and that
a normal script run with distinct IDs still completes the approved workload.
Keep the output aggregate and retain no IDs in the report.

### `VDDAI-REV-002` A poll can overrun the hard job deadline

**MEDIUM - OPEN.** `scripts/run_local_pilot_soak.py` lines 72-103 and
196-241.

The worker observation loop checks the fifteen-second job deadline before
starting a GET. The transport always gives the connection its fixed
four-second operation timeout, even with less job budget remaining. The
response and any successful result are checked only after the blocking
request returns. This fails a late result, but does not stop the activity at
the approved hard deadline.

In the independent simulated timeline, each response took less than the
four-second transport allowance. The runner began its final owner poll at
14.8 seconds and only reported `job_deadline_exceeded` at 18.7 seconds.

Use the remaining absolute monotonic job budget for both upload and owner
readback transport and stop polling and waiting at expiration. Preserve
the safe failure code and single-attempt submission. Closure requires
time-controlled cases covering a late in-flight call, a slow response body,
and a valid timely response. Confirm the measured deadline bounds elapsed
work, in addition to rejecting late results.

### `VDDAI-REV-003` Malformed result values escape sanitized failure reporting

**MEDIUM - OPEN.** `scripts/run_local_pilot_soak.py` lines 216-226 and 288-310
and `scripts/prove_real_inference.py` lines 249-265.

The runner catches `InferenceGateError` from terminal validation. The existing
validator also can raise other type or numeric errors on malformed JSON
objects. These exceptions bypass the runner's safe reason codes and produce
a Python traceback rather than the expected sanitized operator failure.

An independent invocation supplied a valid queue receipt and a malformed
completed response with a list in place of its label. The CLI propagated
`TypeError`. The exclusive aggregate file was written with `result: failed`
and no stable `error` value.

Convert malformed terminal field failures to the soak's stable error
report without exposing response values or traceback detail. Preserve
the existing frozen scoring and shared validation contract. Verify stable
nonzero exit and a sanitized `invalid_terminal_result` receipt for the
malformed label and a malformed numeric case.

## 5. Acceptance coverage

| Criterion | Evidence and result |
| --- | --- |
| Disposable loopback target and exact preflight | The runner hard-codes IPv4 loopback, checks development identity, database health and the requested frozen package before registration. Focused staging-identity rejection and no-redirect cases passed. |
| Fixed local workload and thresholds | Profile, all nine format and size combinations, and nearest-rank p95 checks passed. The accepted distinct job count and hard deadline remain open under `VDDAI-REV-001` and `VDDAI-REV-002`. |
| Safe failure and evidence receipts | The runner uses exclusive output and stops following a normal failed terminal response. Malformed payload error handling remains open under `VDDAI-REV-003`. |
| Measured real inference, queue and resources, bottleneck decision | The Coder independently reported successful warm inference and an active fixed twenty-minute run. Final runtime metrics and the bottleneck decision are pending. |
| Staging release gate | Deferred as stated in the source task. The disposable local evidence cannot satisfy it. |

## 6. Checks run

- Reconciled branch, `HEAD`, merge base, empty index and exact SHA-256.
  `git diff --check` passed. The checkout had the two subject files after
  Coder moved its generated test directories to task scratch storage.
- Ran pinned Windows Python 3.14.3 in a disposable `git archive --format=tar HEAD`
  snapshot with both files overlaid and hash-checked. The cloned interpreter
  loaded the snapshot's runner and inherited no `GIT_*` overrides.
- `python -B -m pytest -q -p no:cacheprovider --tb=short --show-capture=no
  --basetemp <scratch-directory> app/tests/test_local_pilot_soak.py` returned
  **15 passed in 1.76 seconds**.
- Independent synthetic CLI probes reproduced all three findings with fake
  transport and a monotonic clock. The probes made no actual requests.
- Coder exact canonical and strict PostgreSQL verification reported
  **465 passed** and **172 passed** respectively. Those are corroborating
  Coder results. The separate real local Compose soak was still running.

## 7. Checks deferred

The measured local run, sampler, cleanup, and bottleneck evidence will
be reconciled by the responsible role when the receipt is available.
The release candidate's staging workload is the separately deferred
server-dependent gate.

## 8. Remediation handoff

1. Obtain human selection of the open finding IDs.
2. Implement the selected runner closures and verify the reproduced cases,
   unchanged loopback and preflight scope, and stable aggregate evidence.
3. Reconcile the final measured evidence against the exact subject, then
   submit a separately numbered independent re-review. Preserve this
   immutable record. QA follows an eligible verdict.

## 9. Residual context

The target test environment is a disposable local development stack. The
approved fixed workload estimates behavior within that environment, hardware,
and package. The later staging release decision requires its own immutable
candidate, authorization, and evidence.

## Process-learning evidence

| Field | Record |
| --- | --- |
| Observation | All focused tests passed while a synthetic replay could still turn two owner rows into a passing 70-job receipt. |
| Evidence | Independent monotonic and fake-transport probes for `VDDAI-REV-001` through `VDDAI-REV-003`. |
| Impact | The measurement gate must verify the distinct work and actual timing that its own receipt claims. |
| Recurrence | First observed in the fixed-duration pilot runner. |
| Candidate improvement | Exercise a plausible false passing case as well as ordinary failure cases when reviewing a workload acceptance tool. |
| Authority note | This evidence confers no authority to change the workflow or its skills. |
