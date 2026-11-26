# W9D1 correlated structured logging re-review

## 1. Reviewed subject

Review `W9D1-REV-2026-11-27-002`, 27 November 2026. Independent re-review on
`codex/w9d1-correlated-logging` in the W9D1 worktree. `HEAD`, `origin/master`,
the approved base, and the merge base resolved to
`1b9f6160883361bdb99298b256815197ccab8eba`. The committed and staged
ranges were empty. Seven modified and two untracked application and test
files comprised the exact subject. The review records are audit evidence
outside the implementation range.

| Reviewed file | SHA-256 |
| --- | --- |
| `app/api/request_logging.py` (untracked) | `14fdb0037e1d8b588b3a39d6d5881b65d31cfbc295ec2bf315ff387dec1a13d2` |
| `app/api/routes/prediction.py` | `2b0b1f1557d81e4ff83aea39bec02206cea046150dcff01e75edfac17ebf517e` |
| `app/core/logging.py` | `23f5f8e0616b03acc0e378b25b8760398e34d853b5039c4e65787861945c9b91` |
| `app/main.py` | `c82da562d77efac8d2843b507f28bb257c7aa7a5dd3853c6af934dcc2c891297` |
| `app/services/anomaly_inference_service.py` | `49d54bf5e564876ca6367b7c257c29983c9e1b1a96431b24fafcbdfb5a1b5814` |
| `app/tests/test_prediction_api.py` | `e7deebce5d899ab97408787d1909af924e23457ae887b719978cf5d9e1416784` |
| `app/tests/test_prediction_worker_reliability.py` | `dc32e11d45bb64e652c473fed4f0a2da9f42df369a48616f477c597d11f6c805` |
| `app/tests/test_structured_logging.py` (untracked) | `bd4c03f5244fad54b9c536efdff92bc8d12bfc7e93bf0e7006f373827c7b709a` |
| `app/workers/prediction_worker.py` | `32008c9f908302eacd9b28a350a449c10f0b8ef07d8977504342846ae0cad3fd` |

## 2. Contract and acceptance criteria

The approved [W9D1 task](https://app.notion.com/p/3ac0ab50ef6781a1b52ddd59d2dce831)
requires a privacy-safe structured trace across the API, storage, queue,
worker, and database. It also requires end-to-end success and failure
evidence, a documented schema, and a visible commit. The human deferred the
missing book checkpoint and authorized implementation within the approved
W9D1 scope. The later response to the specific remediation request authorized
addressing `VDDAI-REV-001` with regression coverage for both entry points.

The [original review](2026-11-26-w9d1-correlated-logging.md) retains SHA-256
`b84922d258a6ab87a73403e9d7981d5b3a7df06630e8ebff582cae343a8f04a9`.
Its single finding covers redacting application configuration failures from
the supported startup commands. The [repository rules](../../AGENTS.md),
[application rules](../../app/AGENTS.md), and [agent workflow](../engineering/agent-workflow.md)
govern this evidence. The frozen
[inference](../decisions/0003-production-inference-contract.md),
[result persistence](../decisions/0005-inference-result-persistence.md),
[serving](../decisions/0008-registry-selected-production-package.md),
[storage](../decisions/0009-durable-image-storage-boundary.md),
[worker reliability](../decisions/0010-database-backed-prediction-reliability.md),
and [admission](../decisions/0011-database-backed-prediction-admission.md)
boundaries remain applicable.

## 3. Verdict

**PASS.** The one open finding is verified resolved. Independent QA is eligible
on the exact file set above.

## 4. Finding status

| Finding | Severity | Status |
| --- | --- | --- |
| `VDDAI-REV-001` Startup errors bypass credential redaction | `HIGH` | `VERIFIED RESOLVED` |

`app/core/logging.py` lines 191-205 provide the startup guard and emit a
bounded `service.startup_failed` event followed by exit code 1.
`app/main.py` lines 5-11 and `app/workers/prediction_worker.py` lines 13-34
guard the first-party imports that initialize settings and the engine in the
supported processes. `app/tests/test_structured_logging.py` exercises both
service entry points through its parameterized subprocess test.

The reviewer ran the native pinned entry points on an independent scratch
archive with all nine reviewed files overlaid and hash-checked. Module origin
checks verified that the children imported the scratch subject. An invalid
database URL containing a generated synthetic credential fragment reproduced
the original parse failure. An independent invalid storage-backend setting
exercised settings validation before engine setup. Each of four process
executions exited 1, emitted exactly one JSON record with the correct service,
`schema_version=1`, `service.startup_failed`, and `startup_failed`, and left
stderr empty. Both streams were tested for the synthetic value, the scratch
and worktree paths, and traceback text. None appeared. Startup event
correlation fields were null as expected before any request or job exists.

With a valid disposable SQLite configuration and verified worktree module
origins, the native commands returned API `/health/db` HTTP 200 and emitted `worker.started`. The focused integration
and lifecycle suite passed against the same scratch subject. The four-file
remediation preserves healthy imports and application, model, ownership, and
queue behavior. Five implementation files matched the original review
byte-for-byte. No additional actionable finding surfaced.

## 5. Acceptance coverage

| Criterion | Evidence |
| --- | --- |
| Structured request, prediction, job, model, status, and latency fields | The request, API, and worker tests passed against the reviewed schema. The generated request ID links API activity, and the durable prediction/job ID joins the API and worker events. |
| End-to-end success and safe ownership | The focused authenticated upload, real inference-service fixture, persistence, and owner readback test passed. The Coder's separate native-process PostgreSQL trace corroborates the package ID, latency, and authorization outcomes. |
| Safe failure, retry, and settlement logging | The focused storage, queue rollback, retry, ambiguous commit, and stale worker cases passed. The native startup checks verified bounded failures from the two actual executables. |
| Redact tokens, secrets, paths, and payloads | Both startup error classes and both startup entry points passed the private-value scan. The focused runtime log and correlation assertions also passed. |
| Document the schema and lifecycle trace and produce a visible commit | Documentation follows QA. Git actions remain governed by the human approval gate. |

## 6. Checks run

- `git status --short --branch`, `git rev-parse HEAD origin/master`,
  `git merge-base HEAD origin/master`, `git diff --cached --name-only`,
  `git diff --check`, and SHA-256 inspection verified the exact subject and
  the preserved original report.
- With pinned Python 3.14.3 from a disposable interpreter copy, the reviewer
  ran `python -B -m uvicorn app.main:app --host 127.0.0.1 --port 0` and
  `python -B -m app.workers.prediction_worker` under each of two synthetic
  invalid configurations. All four startup assertions passed. The reviewer
  then ran both commands with valid SQLite configuration using a selected
  loopback port for the API. `/health/db` returned 200 and the worker started.
  A first combined run timed out on valid-process readiness while the
  focused tests were running. The separate sequential check passed.
- `python -B -m pytest -q -p no:cacheprovider --tb=short --show-capture=no
  --basetemp <scratch-test-dir> app/tests/test_structured_logging.py
  app/tests/test_prediction_api.py app/tests/test_prediction_worker_reliability.py`
  passed **73 tests in 79.12 seconds** in the scratch archive.
- Coder evidence on the matching files records **429 passed** for
  `.\scripts\verify.ps1 -PythonCommand $Pinned -IncludeFormatting` and
  **171 passed** for `python -B scripts/run_production_gate.py` with no
  skips. Those gates used disposable PostgreSQL 16.15. The Coder also ran a
  separate-process synthetic PostgreSQL prediction trace with owner 200,
  cross-owner 404, and unauthenticated 401.

## 7. Checks deferred

Independent strict PostgreSQL and the separate successful PostgreSQL trace
remain QA verification work. The recorded Coder checks supply corroborating
evidence in this review. The approved task uses reproducible local or CI
verification and excludes live staging from the acceptance test.

## 8. Handoff

There are no open review findings. Independent QA may verify the exact
nine-file subject above. After a current QA pass, Documentation owns the
structured event schema and the sanitized lifecycle example in the maintained
production-readiness guide. The complete proposed subject then goes to the
human Git gate.

## 9. Residual assumptions

The package in the PostgreSQL trace is a deterministic synthetic fixture.
Its public-safe package ID stands in for the deployed package while exercising
the frozen result contract. The application startup guard covers the
first-party configuration and engine import path in the supported CLI process.
On an invalid API import, the process exits 1 with a bounded diagnostic.

## Process-learning evidence

| Field | Record |
| --- | --- |
| Observation | An embedded Python runtime can retain a different worktree on its module path. The reviewer cloned its small runtime into scratch, pointed the clone at the exact reviewed archive, and checked module origins before launching the native commands. |
| Evidence | `VDDAI-REV-001` closure checks and the independent scratch archive described in section 6. |
| Impact | The startup and integration results refer to the exact reviewed source. |
| Recurrence | First observed |
| Candidate improvement | Preserve a module-origin assertion when reviewing a startup behavior on an embedded interpreter. |
| Authority note | This evidence confers no authority to change the workflow or its skills. |
