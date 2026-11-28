# W9D2 service and queue metrics review

## 1. Reviewed subject

Review `W9D2-REV-2026-11-27-001`, 27 November 2026. Independent review of
`codex/w9d2-service-metrics` in the W9D2 worktree. `HEAD` and the
Planner-approved task base and merge base are
`ea3e30c472bf16563cf4ae9c841b1dc687686a0d`. The merge base with
`origin/master` is `1b9f6160883361bdb99298b256815197ccab8eba`. The task-relative
committed and staged ranges are empty. The two untracked files below belong
to the reviewed implementation. This report belongs to the audit record.

| Reviewed file | SHA-256 |
| --- | --- |
| `app/api/request_logging.py` | `7a361e791ee0e88396b8c602cbf0cc18f5b6a7f8bdc8255bfe3ae12a0a716c51` |
| `app/core/config.py` | `42225c32a54456a50ed7f6dbf35afcb6c7523a01cd8a8065c63af85e9d1aff4e` |
| `app/core/logging.py` | `7c7560fb1867e78bcc3bf8cc684420dc98380826233bdede31d5a433fa72d4b4` |
| `app/main.py` | `be1584bcdf624a1f6391c14c9649d21ea2278b380c678304d7bb03940ef65b4d` |
| `app/workers/prediction_worker.py` | `f7bd076b10e1e76fc439c99ad26634cc046a6a846db3dc9072e7263809beaa96` |
| `requirements.txt` | `251dbd1b538622093b5b19eaf03a13008fc39da38eea59b5cde4fd3d8e82b62d` |
| `app/services/metrics_service.py` (untracked) | `3545069d059c14d059015c425f33be5621dfd6f2d20366ee36291992e9249e20` |
| `app/tests/test_observability_metrics.py` (untracked) | `8ad01f3b6fe211f71a129b2dbff64369937ccecbb9d4da82a98d0db90a8d9464` |

## 2. Contract and acceptance criteria

The [W9D2 task](https://app.notion.com/p/3ac0ab50ef6781329af0d44326ed5490)
requires service availability, traffic, latency, errors, and background-job
metrics, an internal or protected endpoint, and simple pilot targets. The
approved plan calls for default-off private API and worker listeners with
bounded labels, a read-only queue aggregate with statement timeout and
overlap deduplication, and worker telemetry grounded in committed lifecycle
events. The proposed pilot targets are API p95 at or below 1 second,
accepted-to-durable-terminal job p95 at or below 15 seconds, inference
p95 at or below 5 seconds, and unexpected failures at or below 1 percent.
Documentation and the approved internal metrics ADR follow an eligible
review and QA. Dashboard infrastructure and a full synthetic workload
belong to later days.

The [repository rules](../../AGENTS.md), [application rules](../../app/AGENTS.md),
and [agent workflow](../engineering/agent-workflow.md) govern the review.
The accepted [inference](../decisions/0003-production-inference-contract.md),
[persistence](../decisions/0005-inference-result-persistence.md),
[worker reliability](../decisions/0010-database-backed-prediction-reliability.md),
[admission](../decisions/0011-database-backed-prediction-admission.md),
and [staging boundaries](../decisions/0014-single-host-staging-environment.md)
remain applicable.

## 3. Verdict

**CHANGES REQUIRED.** The normal metrics traces passed. The implementation
undercounts durable job duration, can report a failed worker poll as ready, and
lets one exporter startup failure abort either service.

## 4. Findings

### `VDDAI-REV-001` Job duration omits database settlement time

**HIGH Â· OPEN.** `app/workers/prediction_worker.py` lines 77-80, 626-644,
and the analogous terminal-failure paths.

The worker captures `now` before settlement and calculates duration before
`db.commit()`. The counter correctly waits for commit to return, but the
histogram receives the earlier duration. A worker can therefore report a
job within the 15-second pilot target while the terminal result is still
unavailable because of database lock or commit time.

In an independent in-memory fixture, the prediction was queued ten seconds
before processing and the clock advanced another thirty seconds during
terminal commit. The persisted row completed and the exporter recorded
`10.0` seconds for a `40.0`-second acceptance-to-durable-terminal interval.

Capture the duration from the existing acceptance timestamp to the observed
successful terminal commit on each applicable success and failure branch.
Preserve the recorded lifecycle timestamps, locking, and persistence
semantics. Closure requires a simulated slow lock or commit that falls on
the correct side of the 15-second histogram bucket, plus assertions for
normal success, terminal failure, and no terminal duration sample after a
failed or ambiguously observed commit.

### `VDDAI-REV-002` An idle claim masks a recovery failure in worker readiness

**MEDIUM Â· OPEN.** `app/workers/prediction_worker.py` lines 330-343, 378-387,
and 674-696, with `app/services/metrics_service.py` lines 148-151 and 236-237.

Recovery commit failure correctly rolls back and sets the readiness gauge
to zero. The same poll proceeds to the claim query, and the empty result
sets readiness back to one. An expired job whose recovery continues to fail
can be paired with a healthy readiness gauge indefinitely.

The local reproduction seeded an expired processing row, made recovery
commit raise `SQLAlchemyError`, and verified the row stayed processing with
no retry scheduled. The same invocation emitted `recovery_failed` and
exposed `vddai_worker_ready 1.0`.

Base the readiness sample on the outcome of the required steps of one worker
poll. Preserve the current recovery and claim behavior. Closure requires
a failed recovery with an empty subsequent claim to remain unready, a later
complete successful idle poll to become ready, and ordinary claim, retry,
and settlement assertions to continue passing.

### `VDDAI-REV-003` An optional exporter startup error aborts API or worker startup

**MEDIUM Â· OPEN.** `app/services/metrics_service.py` lines 274-292,
`app/main.py` lines 16-25, and `app/workers/prediction_worker.py` lines 783-800.

The pinned Prometheus server starts a thread after allocating the HTTP server.
Thread creation can raise `RuntimeError`. The optional listener handles
`OSError` and `ValueError`, so this startup error escapes into the API lifespan
or the worker's fatal startup boundary instead of the optional diagnostic.
Core service availability should survive failure to start an opted-in exporter.

With the server start call set to raise a synthetic `RuntimeError`, both
service contexts propagated the exception. The source shows that the
underlying Prometheus implementation calls `Thread.start()` directly.

Contain exporter initialization and thread-start failures at the optional
boundary, clean up any partially opened listener, and emit the stable safe
diagnostic. Closure requires a synthetic thread-start error for each
service to leave the API lifespan or worker loop running with metrics
unavailable, with no raw error text in logs and no leftover listener.

## 5. Acceptance coverage

| Criterion | Evidence and result |
| --- | --- |
| Request rate, errors, and latency with bounded labels | Source review found registered route templates and finite method and status classes. The private listener test exercised success, unmatched paths, and a synthetic query sentinel. Focused assertions passed. |
| Internal endpoint and disabled default | An actual loopback listener served the registry while the application route `/metrics` returned 404. Address selection rejects wildcard and non-RFC1918 values in container mode. The optional failure boundary remains open under `VDDAI-REV-003`. |
| Queue depth, age, and database state | Queue collection derives depth and oldest accepted age from one grouped query and uses a lock to deduplicate overlapping database reads. PostgreSQL applies a local statement timeout. Local state and outage tests passed. |
| Committed claims, retries, terminal outcomes, execution failures, and inference latency | Focused tests passed for retry, terminal outcomes, and frozen inference latency. The total job latency and worker readiness used for the pilot remain affected by `VDDAI-REV-001` and `VDDAI-REV-002`. |
| Pilot targets, documentation, and visible commit | The engineering guide and ADR follow a current QA pass, and the proposed subject then reaches the human Git gate. |

## 6. Checks run

- `git status --short --branch`, `git rev-parse HEAD origin/master`,
  `git merge-base HEAD origin/master`, `git merge-base HEAD <approved-task-base>`,
  `git diff --cached --name-only`, `git diff --check`, and SHA-256 comparison
  confirmed the exact eight-file worktree subject.
- A byte-safe decoded comparison with `git show HEAD:requirements.txt`
  verified the existing UTF-16LE BOM and the sole added line
  `prometheus-client==0.26.0`. Installed package metadata reports that version.
  Inspection of its pinned server implementation confirmed `Thread.start()`
  and the default quiet HTTP request handler.
- In a disposable archive from `git archive --format=tar HEAD` with the eight
  verified files overlaid, pinned Python 3.14.3 ran `python -B -m pytest -q
  -p no:cacheprovider --tb=short --show-capture=no --basetemp <scratch-test-dir>
  app/tests/test_observability_metrics.py app/tests/test_structured_logging.py
  app/tests/test_prediction_worker_reliability.py`. **35 passed in 32.51 seconds**.
  The archive had independent interpreter module origins and SQLite data.
  Child processes inherited no Git environment overrides.
- Targeted in-memory reviewer probes in that archive observed the three
  counterexamples above. Both listener contexts escaped on synthetic thread
  failure, the expired recovery failure exported ready `1.0`, and the 40-second
  committed job exported `10.0` seconds.
- The Coder's verification on the matching files recorded **434 passed** for
  `.\scripts\verify.ps1 -PythonCommand $Pinned -IncludeFormatting` and **171
  passed** for `python -B scripts/run_production_gate.py` on disposable
  PostgreSQL 16.15. The Coder also ran a native API and worker process trace
  with private metrics, queue and terminal changes, and owner authorization.

## 7. Checks deferred

The Coder's canonical gate, strict PostgreSQL gate, and successful
separate-process PostgreSQL trace provide corroborating evidence. Independent
QA should exercise the eligible remediated subject. Live staging and a
dashboard deployment are outside this review.

## 8. Remediation handoff

1. Obtain human selection of the open findings from this review.
2. Address `VDDAI-REV-001`, `VDDAI-REV-002`, and `VDDAI-REV-003` within the
   approved scope and execute the closure checks for each selected finding.
3. Submit the exact updated range for independent numbered re-review.
   Preserve this report. QA follows an eligible verdict.

## 9. Residual context

The pilot metrics are process-local and counters reset on restart. Model
readiness is unknown before real worker package or inference evidence.
Private endpoint configuration still belongs to the reviewed deployment
boundary. The proposed target values are pilot targets and require measured
evidence from the later workload.

## Process-learning evidence

| Field | Record |
| --- | --- |
| Observation | The passing focused suite measured successful metric emission. Small injected cases exposed errors in the meaning of the samples and the optional exporter boundary. |
| Evidence | `VDDAI-REV-001` through `VDDAI-REV-003` and the targeted probes in section 6. |
| Impact | The pilot targets and availability signals need behavioral evidence at the transaction and exporter boundaries. |
| Recurrence | First observed for service metrics. |
| Candidate improvement | Validate the reported value across slow commit, failed recovery, and failed optional startup when reviewing corresponding instrumentation. |
| Authority note | This evidence confers no authority to change the workflow or its skills. |
