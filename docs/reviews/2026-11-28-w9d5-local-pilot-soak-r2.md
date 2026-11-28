# W9D5 local pilot soak re-review

## 1. Reviewed subject

Review `W9D5-REV-2026-11-28-002`, 28 November 2026. Independent
re-review of `codex/w9d5-local-pilot-soak` in the standalone W9D5
checkout. The approved parent and `HEAD` are
`8f21330084c9a605c5e0e661b6c7f7c21d68a4cc`. The merge base with
`origin/master` is `1b9f6160883361bdb99298b256815197ccab8eba`.
The task-relative committed and staged ranges are empty. Two untracked
Python files form the implementation subject. Review reports are separate
audit evidence.

| Reviewed file | SHA-256 |
| --- | --- |
| `scripts/run_local_pilot_soak.py` | `5ff20ded07219f7c1a7c6f586a6aa70d3e3320531cb5e8af4c90e5f58f7545e4` |
| `app/tests/test_local_pilot_soak.py` | `f38862ce05645c820740c495094253d2d2e15edd4f03409ba3bc2ba95a929e2e` |

## 2. Contract and selected findings

The approved [W9D5 task](https://app.notion.com/p/3ac0ab50ef678166b189eacf3ada6840)
requires a defined workload, measured latency and failures, queue behavior
and resource evidence, and an evidenced pilot envelope. Its immutable
candidate staging soak remains a deferred server-dependent release gate.

The approved local workload uses two synthetic owners on a disposable
development stack and three image formats over three sizes. It schedules
ten jobs across five minutes and sixty across fifteen minutes. Targets
are API p95 at most 1 second, submission-to-observed-terminal p95 at most
15 seconds, inference p95 at most 5 seconds, unexpected failures at most
1 percent, and a hard per-job deadline of 15 seconds.

The human approved remediation of `VDDAI-REV-001` through `VDDAI-REV-003`.
The [original review](2026-11-28-w9d5-local-pilot-soak.md) remains preserved
at SHA-256 `77aa6516f4bf434e4fab1333edb6b117c870e23eafbef3fd85fcdb44dc6580c7`.
The [repository rules](../../AGENTS.md), [application rules](../../app/AGENTS.md),
[workflow](../engineering/agent-workflow.md),
[prediction reliability decision](../decisions/0010-database-backed-prediction-reliability.md),
and [private metrics decision](../decisions/0015-private-observability.md)
apply.

## 3. Verdict

**PASS for the approved local subject.** All prior findings are verified
resolved. The measured local run satisfies the fixed workload and latency
limits. Independent QA is eligible on the exact fingerprinted files.
The staging-dependent release gate remains deferred.

## 4. Finding status

| ID | Severity | Status |
| --- | --- | --- |
| `VDDAI-REV-001` Reused queue receipt IDs can produce a passing workload | `HIGH` | `VERIFIED RESOLVED` |
| `VDDAI-REV-002` A poll can overrun the hard job deadline | `MEDIUM` | `VERIFIED RESOLVED` |
| `VDDAI-REV-003` Malformed result values escape sanitized failure reporting | `MEDIUM` | `VERIFIED RESOLVED` |

### `VDDAI-REV-001`

The runner requires HTTP 202 with exact queued state and a positive integer
ID that is unique across the whole run. The set covers both owners and both
phases. Replayed IDs fail before they can increment the accepted count or
trigger another readback. The operator receipt remains aggregate.

The independent retest sent the same two recycled owner IDs as R1. It
rejected the third receipt, exited 1 with `duplicate_queue_receipt`,
and counted two completions. A positive ID with non-queued status was
rejected before counting acceptance. Focused regressions also passed for
a duplicate across phases and the fixed 70-job valid schedule. The actual
timed run's separate PostgreSQL aggregate reconciled 70 distinct workload
rows and one preflight row.

### `VDDAI-REV-002`

The upload and all owner reads share one monotonic cutoff for each job.
Each exchange uses the earlier of that cutoff and the four-second
request cap. Async cancellation covers connection, headers, body, and
transport cleanup. The body is bounded and poll sleep is clipped to
remaining job time. The client retains literal loopback, disabled
redirects and ambient proxies, and single submission.

Independent focused loopback tests cancelled a stalled POST while waiting
for headers and a GET whose body kept arriving in pieces. The clipped
poll-sleep case stopped at the job deadline. The timely response and
shared upload and readback deadline cases passed.

### `VDDAI-REV-003`

Terminal validation converts malformed field types and numeric conversion
failures to `invalid_terminal_result`. The frozen scoring and model
lineage validation stays in the reused validator. Exact terminal identity
still has to match the accepted queue receipt and package.

Independent malformed label and oversized numeric probes each exited 1
with the stable reason and a failed aggregate receipt. The fixture's
private marker was absent and stderr was empty. The focused suite also
passed the oversized inference-latency case.

No new actionable findings surfaced.

## 5. Measured local result

The Coder's disposable Compose proof used mounted source based on
`8f21330084c9a605c5e0e661b6c7f7c21d68a4cc`, the exact runner SHA above,
local application image ID
`sha256:86fe698871dc878b850f694fa7e0c74c77a74975c0af7e30eeb5f6b255ed0ac3`,
and frozen package `mvtec-tile-resnet18-knn-fe64db2228370b2d`. The timed
workload took 1,200.147 seconds and completed 10 warmup jobs and 60 steady
jobs. The separate SQL aggregate confirmed 71 distinct completed rows,
one of them the warm proof. It also recorded three synthetic owners
including the preflight owner, zero failed rows, one model version, and
maximum attempt count one.

| Metric | Observed | Approved limit |
| --- | --- | --- |
| API p95 across 374 measured requests | 0.110 seconds | At most 1 second |
| Submission to observed terminal p95 | 1.584 seconds | At most 15 seconds |
| Persisted inference p95 | 0.175 seconds | At most 5 seconds |
| Unexpected failures | 0 of 70, or 0 percent | At most 1 percent |

At the 15-second sampling cadence the queue peaked at one queued and
one active job with zero waiting retries. The final queue was drained.
All six services had 70 successful resource samples. The highest sampled
CPU was API at 69.95 percent. Grafana had the highest sampled memory at
552.1 MiB. The receipt also records private API and worker scrapes,
authenticated Grafana, twelve panels, ten rules, and scoped cleanup of
the project and 71 disposable uploads.

The local envelope exercised four steady jobs per minute with one
outstanding measured client job. The largest measured latency is the
end-to-end path. Its timing combines request, queue, inference, and
readback intervals. Sustained concurrency, saturation, and detailed delay
attribution remain work for the separately authorized staging release gate.

## 6. Checks run

- Reconciled branch, approved parent, merge base, empty index,
  `git diff --check`, both implementation SHA-256 values, and the
  preserved R1 checksum.
- Ran an independent hash-matched `git archive --format=tar HEAD` snapshot
  of both files with the cloned pinned Python 3.14.3 runtime. The
  disposable runner inherited no `GIT_*` overrides and used its own
  forward-slash pytest base-temp path.
- `python -B -m pytest -q -p no:cacheprovider --tb=short --show-capture=no
  --basetemp <scratch-directory> app/tests/test_local_pilot_soak.py`
  reported **26 passed in 3.93 seconds**. Independent
  clock and fake transport probes also verified the original duplicated
  receipts and malformed terminal cases.
- Independently verified all seven entries in the Coder's `SHA256SUMS.txt`.
  The measured receipt `soak-evidence.json` is
  `9a45c0acad346a6860f222237e197d1122413a9618ef45f5a3eede1b38afb146`,
  `load-report.json` is
  `ce91e1dd998d06111bf2c61159d0f3dfde56b4dedf683f31e69a7b2d62d06a47`,
  `resources.json` is
  `8ab249e7844af59e53a66bd291f635a1467e95c5983243ff95ca6cbe5e15407a`,
  and full `local-rehearsal.txt` is
  `bd7a54bf68c290c6af21509e9cc933f9448a3a127fefaf82077650b8436db9ae`.
  The archived proof driver matched
  `412cbc67f6feca37c2a643ee6f2555aca6418ee9aa6aee433d0d2cb81158cd8b`.
  Verified that the receipt binds the exact runner and reconciles phase
  counts, client samples, SQL totals, queue, resources, and cleanup.
- The Coder's canonical gate reported **476 passed in 112.67 seconds**.
  The separate disposable PostgreSQL strict gate reported **172 passed**
  in 54.66 seconds with 304 deselected and zero skips. The Compose
  configuration projection passed. These are corroborating Coder checks.

## 7. Checks deferred

The real Docker workload and SQL receipt are Coder runtime evidence. The
Reviewer independently verified their hashes and reconciled their
reported results. The independent QA role remains next. The staged
release-candidate capacity gate is separately deferred under the task.

## 8. Handoff

Independent QA may verify the exact fingerprinted local subject, the three
remediation paths, and the durable timed evidence. Documentation can then
publish the supported local envelope and outstanding staging gate.
Git actions follow their existing human gate.

## 9. Residual context

The results characterize this fixed workload, local hardware, and frozen
package. Queue and service resource observations are samples. The fixture's
preflight job is counted separately from the measured 70 jobs.

## Process-learning evidence

| Field | Record |
| --- | --- |
| Observation | The passing workload receipt independently reconciled with the database's distinct rows and with the exact runner hash. |
| Evidence | `VDDAI-REV-001` closure probes, the timed receipt and its SQL aggregate. |
| Impact | The result ties the reported duration and job count to real persisted work. |
| Recurrence | First observed for this workload re-review. |
| Candidate improvement | Keep an independent distinct persisted-row check alongside future workload runners that report accepted and completed counts. |
| Authority note | This evidence confers no authority to change the workflow or its skills. |
