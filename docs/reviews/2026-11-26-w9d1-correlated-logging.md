# W9D1 correlated structured logging review

## 1. Reviewed subject

Review `W9D1-REV-2026-11-26-001`, 26 November 2026. Independent review of the
application, worker, and tests on `codex/w9d1-correlated-logging` in the
`visual-defect-ai-backend-w9d1` worktree. The approved Planner base, `origin/master`,
`HEAD`, and merge base all resolved to `1b9f6160883361bdb99298b256815197ccab8eba`.
The committed and staged ranges were empty. Seven modified and two untracked
implementation files comprised the exact reviewed subject. This review report
is audit evidence outside that subject.

| Reviewed file | SHA-256 |
| --- | --- |
| `app/api/request_logging.py` (untracked) | `14fdb0037e1d8b588b3a39d6d5881b65d31cfbc295ec2bf315ff387dec1a13d2` |
| `app/api/routes/prediction.py` | `2b0b1f1557d81e4ff83aea39bec02206cea046150dcff01e75edfac17ebf517e` |
| `app/core/logging.py` | `39f481f6b95bf41a094adf5b03025d0a71e905486063e9a24ac304d80f14248a` |
| `app/main.py` | `1a16a741b0b7b322252e180beaf7963e3eeef890badf79f17ba7193ab0794365` |
| `app/services/anomaly_inference_service.py` | `49d54bf5e564876ca6367b7c257c29983c9e1b1a96431b24fafcbdfb5a1b5814` |
| `app/tests/test_prediction_api.py` | `e7deebce5d899ab97408787d1909af924e23457ae887b719978cf5d9e1416784` |
| `app/tests/test_prediction_worker_reliability.py` | `dc32e11d45bb64e652c473fed4f0a2da9f42df369a48616f477c597d11f6c805` |
| `app/tests/test_structured_logging.py` (untracked) | `a0b7e81f8c940ea6f9d5554defb464d4593fc2eaf4ed809414f15df0773b716f` |
| `app/workers/prediction_worker.py` | `9b8cb49788ba8f81eb91f5cb97619f17395896b5657422a0428b2ea8fdb91d89` |

## 2. Contract and acceptance criteria

The [W9D1 task](https://app.notion.com/p/3ac0ab50ef6781a1b52ddd59d2dce831)
requires a trace across API, storage, queue, worker, and database. Its
definition of done includes six explicit structured fields, credential and
payload privacy, and end-to-end correlation and failure verification. It
requires a documented schema, a lifecycle trace, and a visible commit. The
invoking human explicitly directed the task to continue with available
evidence and deferred the Chapters 8â€“11 reading checkpoint. The approved
Planner handoff and Coder report bound this pass to local implementation
and verification.

Repository authorities include the [root instructions](../../AGENTS.md), the
[application instructions](../../app/AGENTS.md), the
[agent workflow](../engineering/agent-workflow.md), and the accepted decisions
for [inference](../decisions/0003-production-inference-contract.md),
[result persistence](../decisions/0005-inference-result-persistence.md),
[serving selection](../decisions/0008-registry-selected-production-package.md),
[image storage](../decisions/0009-durable-image-storage-boundary.md),
[worker reliability](../decisions/0010-database-backed-prediction-reliability.md),
and [prediction admission](../decisions/0011-database-backed-prediction-admission.md).

## 3. Verdict

**CHANGES REQUIRED.** The independent focused trace and worker tests passed.
A startup error in either supported application process can put protected
database configuration material in stderr before the new guards execute.
This prevents the reviewed subject from satisfying the redaction criterion.

## 4. Findings

### `VDDAI-REV-001` â€” Startup errors bypass credential redaction

| Field | Value |
| --- | --- |
| Severity | `HIGH` |
| Status | `OPEN` |
| Primary location | `app/main.py` lines 5â€“15 and `app/workers/prediction_worker.py` lines 15â€“16 and 710â€“726 |
| Shared configuration boundary | `app/db/session.py` lines 3â€“9 |

The API configures safe Uvicorn logging inside its lifespan hook. Resolving
the application already imports the route modules and initializes the database
engine. The worker similarly imports `SessionLocal` before reaching its
`main()` exception boundary. A failure during either import bypasses the new
redaction and diagnostic code. The fatal worker test at
`app/tests/test_structured_logging.py` lines 155â€“168 injects a failure after
module import and therefore misses this case.

I ran the documented Uvicorn and worker entry points in separate local
subprocesses using a disposable database configuration with an invalid DSN
and a generated synthetic credential marker. The invalid configuration
failed before any database connection. Each process exited with code 1 and
wrote a raw traceback with the exact synthetic credential fragment. The
first malformed-port probe also found zero structured diagnostics from
either process. The probes emitted only Boolean match results to review
evidence. The source-level import order existed at the base and the leak
survives the W9D1 entry-point changes.

Service stderr is commonly retained alongside stdout. A boot failure can
therefore retain credential material in the same operational sink as the
new privacy-safe trace. Redaction must cover application configuration
failures at the normal API and worker entry points.

Apply the same credential and path disclosure boundary before settings
and database initialization can render raw errors. Preserve the existing
nonzero failure behavior and an actionable safe diagnostic for these
failures. Closure requires subprocess coverage against both supported entry
points with a generated synthetic credential marker in malformed startup
configuration. Check both streams for absence of the marker and raw
traceback or private paths and verify that the exit remains nonzero with
a bounded diagnostic. Re-run the valid startup, runtime redaction, and
correlated success and failure cases.

## 5. Acceptance coverage

| Criterion | Review evidence | Result |
| --- | --- | --- |
| Stable structured request, prediction, job, model, status, and latency fields | `app/core/logging.py` emits schema version 1. `app/api/request_logging.py` uses one generated ID per request and resets the context. `app/api/routes/prediction.py` joins successful enqueue and authorized single-row readback using the identical durable prediction and job ID. `app/workers/prediction_worker.py` carries that ID, attempt, and result package identity. | Covered for the exercised path |
| Trace upload, queue, claim, storage read, inference, durable terminal result, and owner readback | `test_authenticated_upload_worker_and_readback_use_real_inference_path` passed independently. The Coder handoff also reports a separate local Uvicorn, worker, and PostgreSQL 16.15 trace for one synthetic job with owner `200`, cross-owner `404`, and unauthenticated `401`. | Covered |
| Preserve safe failures and retry/fencing semantics | Independent focused tests passed for enqueue rollback and orphan cleanup, missing input, transient storage retry, ambiguous result commit observation, and stale-attempt discard. Source comparison preserves admission, claim, and settlement transaction boundaries and the frozen result and lineage contract. The Coder reported `171` strict PostgreSQL tests passed without skips. | Covered for the exercised paths |
| Redact tokens, secrets, sensitive paths, and payload data | Independent tests passed for application event fields, Uvicorn request and runtime error filtering, parallel request isolation, missing ownership, and synthetic sentinels from the inference path. Both supported process startups disclosed synthetic credential material on invalid configuration. | Unmet. `VDDAI-REV-001` |
| Document the schema and an example trace, then produce a visible commit | Documentation belongs to the stage after QA. The human-controlled Git decision follows the eligible documentation delta. | Pending downstream gates |

## 6. Checks run

- `git status --short --branch`, `git rev-parse HEAD origin/master`,
  `git merge-base HEAD origin/master`, `git diff --cached --name-only`,
  `git ls-files --others --exclude-standard`, and `git diff --check` confirmed
  the exact subject and a clean staged range. SHA-256 checks on all nine
  reviewed files matched the Coder handoff.
- Pinned Windows Python 3.14.3, `python -B -m pytest -q -p no:cacheprovider
  --tb=short --show-capture=no --basetemp <scratch-test-dir>
  app/tests/test_structured_logging.py app/tests/test_prediction_api.py
  app/tests/test_prediction_worker_reliability.py` passed **71 tests in
  32.04 seconds**. The temporary subject came from `git archive --format=tar HEAD`
  with the nine hash-checked files overlaid. It used its own SQLite fixture
  database and contained no local environment file.
- `python -B -m uvicorn app.main:app --app-dir <review-worktree> --host 127.0.0.1`
  and `python -B -m app.workers.prediction_worker` with synthetic invalid
  configuration both exited `1`. A captured-stream comparison detected the
  synthetic credential fragment and traceback for each entry point. The
  reported output contains only the process names and comparison results.
- The Coder handoff records `.\scripts\verify.ps1 -PythonCommand $Pinned
  -IncludeFormatting` with **427 passed**, and `python -B
  scripts/run_production_gate.py` with **171 passed** and zero skips. Those
  results came from the Coder using a disposable PostgreSQL 16.15 database and
  are corroborating evidence.

## 7. Checks deferred

Independent strict PostgreSQL and separate-process successful synthetic
inference rely on the cited Coder runs for this review. Independent QA can
exercise them on the eligible re-reviewed range. The supported CLI
subprocess probes used local resources. Hosted CI and live staging are
outside the W9D1 local evidence requirement.

## 8. Remediation handoff

1. Obtain the human selection for `VDDAI-REV-001` as required by the agent
   workflow.
2. Apply the bounded startup redaction change and complete the two-process
   closure check and applicable regression gates.
3. Submit the updated subject and exact evidence for independent re-review.
   This report and its finding ID remain immutable. QA follows an eligible
   re-review verdict.

## 9. Residual assumptions

The delegated Coder evidence uses deterministic synthetic inference and
does not measure a deployed model. The repository-approved meaning of result
`model_version` remains the frozen package ID. Its selected registry version
continues to be available through the existing `/health/model` contract.
A manifest and event schema explanation belong in the Documentation handoff.

## Process-learning evidence

| Field | Record |
| --- | --- |
| Observation | The fatal worker unit test exercised an exception after import. The independently launched API and worker processes also exercised the settings and engine import path and exposed an earlier redaction gap. |
| Evidence | `VDDAI-REV-001`, the separate-process probes, and `app/tests/test_structured_logging.py` lines 155â€“168 |
| Impact | Testing only a directly invoked entry-point function can miss diagnostics emitted before that function or the API lifespan runs. |
| Recurrence | First observed |
| Candidate improvement | When startup redaction is within an approved task, verify it using the supported process commands and a synthetic configuration marker. |
| Authority note | This evidence confers no authority to change the workflow or its skills. |
