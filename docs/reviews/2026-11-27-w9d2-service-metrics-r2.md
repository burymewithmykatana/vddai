# W9D2 service and queue metrics re-review

## 1. Reviewed subject

Review `W9D2-REV-2026-11-27-002`, 27 November 2026. Independent re-review of
`codex/w9d2-service-metrics` in the W9D2 worktree. `HEAD` and the approved
task base and merge base are `ea3e30c472bf16563cf4ae9c841b1dc687686a0d`.
The merge base with `origin/master` is `1b9f6160883361bdb99298b256815197ccab8eba`.
The task-relative committed and staged ranges are empty. Six modified and
two untracked implementation and test files form the reviewed subject.
The original and current reports are audit evidence outside that range.

| Reviewed file | SHA-256 |
| --- | --- |
| `app/api/request_logging.py` | `7a361e791ee0e88396b8c602cbf0cc18f5b6a7f8bdc8255bfe3ae12a0a716c51` |
| `app/core/config.py` | `42225c32a54456a50ed7f6dbf35afcb6c7523a01cd8a8065c63af85e9d1aff4e` |
| `app/core/logging.py` | `7c7560fb1867e78bcc3bf8cc684420dc98380826233bdede31d5a433fa72d4b4` |
| `app/main.py` | `be1584bcdf624a1f6391c14c9649d21ea2278b380c678304d7bb03940ef65b4d` |
| `app/workers/prediction_worker.py` | `30758368350ba3dda494df09ff7a0c475357ce2cde3245e5958d9b8f06a53468` |
| `requirements.txt` | `251dbd1b538622093b5b19eaf03a13008fc39da38eea59b5cde4fd3d8e82b62d` |
| `app/services/metrics_service.py` (untracked) | `8c800ac1db4e6c7b94346a744cd0bab71aee2dddc86491ace81b9dae330c688f` |
| `app/tests/test_observability_metrics.py` (untracked) | `7cfc99fe51b3757fa7553070aac18a9cb5d98b13c6ef0974a792b8b7a0154702` |

## 2. Contract and selected findings

The approved [W9D2 task](https://app.notion.com/p/3ac0ab50ef6781329af0d44326ed5490)
requires service requests, job and inference latency, failures, retries,
queue state, and readiness metrics at a protected or internal endpoint.
The approved plan includes default-off private listeners, bounded labels,
a read-only bounded database queue query, and job duration through durable
terminal settlement. The proposed p95 targets are at most 1 second for API
requests, 15 seconds for accepted-to-durable-terminal jobs, and 5 seconds for
inference. Unexpected failures have a target of at most 1 percent.

The human selected `VDDAI-REV-001` through `VDDAI-REV-003` from the
[original review](2026-11-27-w9d2-service-metrics.md). Its preserved SHA-256
is `18687d92cd42edc75a9327bf9d651047d1ca16fdbbdd10cab82bcd8af7046a14`.
Three files changed since that review and five fingerprinted files still
match. The [repository rules](../../AGENTS.md),
[application rules](../../app/AGENTS.md), and
[agent workflow](../engineering/agent-workflow.md) govern the review.
The accepted [persistence](../decisions/0005-inference-result-persistence.md),
[worker reliability](../decisions/0010-database-backed-prediction-reliability.md),
[admission](../decisions/0011-database-backed-prediction-admission.md),
and [staging boundaries](../decisions/0014-single-host-staging-environment.md)
remain applicable.

## 3. Verdict

**PASS.** All three prior findings are verified resolved. Independent QA
is eligible on the exact eight-file subject above.

## 4. Finding status

| ID | Severity | Status |
| --- | --- | --- |
| `VDDAI-REV-001` Job duration omits database settlement time | `HIGH` | `VERIFIED RESOLVED` |
| `VDDAI-REV-002` An idle claim masks a recovery failure in worker readiness | `MEDIUM` | `VERIFIED RESOLVED` |
| `VDDAI-REV-003` An optional exporter startup error aborts API or worker startup | `MEDIUM` | `VERIFIED RESOLVED` |

### `VDDAI-REV-001`

The worker captures the existing acceptance timestamp before settlement
and samples duration after a successful terminal commit returns. A retry
or an ambiguously committed row observed during reconciliation yields no
terminal observation. The instrumentation preserves persisted timestamps,
transaction boundaries, and attempt fencing.

An independent clock-injected fixture recorded 40 seconds for the delayed
commit scenario that exported 10 seconds in R1. Its 15-second histogram
bucket remained at zero and the persisted completion timestamp matched the
existing lifecycle value. A separate expired-attempt terminal recovery
also produced exactly one failure at 40 seconds, with no observation in
the 15-second bucket. The four-case repository regression confirmed
successful completion, terminal execution failure, rejected commit,
and an ambiguously committed result.

### `VDDAI-REV-002`

Readiness now reflects the outcome at the recovery-plus-claim poll
boundary. A failed recovery or claim marks that poll failed. The empty
claim branch leaves that state intact and the worker retains its existing
claim control flow.

An independent fixture injected a recovery commit failure for an expired
job. Its row stayed in processing with no retry scheduled, and readiness
stayed at zero through the same invocation's idle claim. A later successful
poll committed the retry schedule and restored readiness to one.

### `VDDAI-REV-003`

The optional exporter owns the bound HTTP server before starting the
thread. A thread-start error closes the socket, emits the stable
`service.metrics_unavailable` diagnostic, and leaves the service
without an active exporter.

The reviewer injected failure after a real loopback bind for both service
registries. Each service emitted one sanitized diagnostic and released
the exact port, which a new socket could bind. The focused positive
startup fallback cases confirmed API health and entry into the worker
loop. The private scrape and public `/metrics` 404 cases also passed.

No new actionable findings surfaced.

## 5. Acceptance coverage

| Criterion | Evidence |
| --- | --- |
| Request rate, errors, and latency with bounded labels | The HTTP route-template boundary is preserved. The focused tests verify that the private API scrape exposes requests and excludes synthetic sensitive values. |
| Queue depth and age, worker readiness, and failures | The grouped queue snapshot and overlap lock are preserved. The independent poll tests verified readiness and recovery semantics. |
| Job and inference durations, retries, and terminal outcomes | Delayed settlement, ambiguous commit, expired recovery, retry, and ordinary inference cases passed. Inference still uses the frozen result latency. |
| Protected or internal endpoint | Default-off and private address handling passed. The optional failure regression and actual port-rebind probes verified service fallback. |
| Demo targets and operator documentation | Documentation records the schema and approved targets after QA. The separate measured workload will assess the targets. The Git action follows its human gate. |

## 6. Checks run

- Verified the exact file set and preserved R1 checksum with Git branch,
  base, merge-base and index inspection, `git diff --check`, and SHA-256
  comparison before and after the independent run.
- Created a disposable `git archive --format=tar HEAD` snapshot and
  overlaid and hash-checked the eight reviewed files. The cloned pinned
  Python 3.14.3 runtime used this snapshot, separate SQLite data, and a
  process environment cleared of `GIT_*` overrides.
- Independent in-memory and loopback probes observed the two released
  ports, failed-then-successful retry recovery readiness, and 40-second
  durable completion and terminal failure with the correct histogram
  bucket.
- Ran `python -B -m pytest -q -p no:cacheprovider --tb=short
  --show-capture=no --basetemp <scratch-test-dir>
  app/tests/test_observability_metrics.py app/tests/test_structured_logging.py
  app/tests/test_prediction_worker_reliability.py`. Pytest reported
  **41 passed in 49.81 seconds**.
- The Coder reported **433 passed and 7 PostgreSQL-dependent skips** from
  `.\scripts\verify.ps1 -PythonCommand $Pinned -IncludeFormatting` and
  **171 passed** with zero skips from `python -B
  scripts/run_production_gate.py` against disposable PostgreSQL 16.15.
  Those runs corroborate the independently verified evidence.

## 7. Checks deferred

Independent strict PostgreSQL and a separate-process trace are downstream
QA work. Hosted CI and live deployment are outside this review. The
later dashboard and workload tasks use their own approval boundaries.

## 8. Handoff

Independent QA may exercise the exact fingerprinted range. Verify the
three closure scenarios alongside queue, HTTP, inference, and privacy
regressions and the local PostgreSQL evidence. Documentation follows a
current QA pass.

## 9. Residual context

The counters are process-local and reset on restart. Readiness reflects
the latest completed queue poll. Model readiness remains unknown pending
worker evidence. The approved pilot workload supplies evidence against
the proposed targets.

## Process-learning evidence

| Field | Record |
| --- | --- |
| Observation | The original fault probes established closure against the exact reviewed range. The reviewer also checked a terminal recovery and an actual port rebind. |
| Evidence | Independent checks for `VDDAI-REV-001` through `VDDAI-REV-003` in sections 4 and 6. |
| Impact | Metric values and listener resource release are independently observable. |
| Recurrence | First observed for this re-review. |
| Candidate improvement | Retain the original reproducible input and check the observable result when verifying observability remediation. |
| Authority note | This evidence confers no authority to change the workflow or its skills. |
