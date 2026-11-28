# Production Security and Reliability Readiness

- Status: Current
- Scope: v0.1.0 MVTec AD `tile` pilot
- Gate: W7D4 production security and reliability

## Purpose

This document defines the repeatable pre-release gate for the authenticated
prediction path. It records current operational risks and release conditions;
it does not replace executable tests, accepted ADRs, independent review, QA,
or human deployment approval.

Run the gate only against a disposable local or test environment. The deployed
probe creates users, prediction history, and a stored image. It accepts only an
API whose `/health` response identifies the environment as `development` or
`test`; every other identity fails before the first mutating request.

## Gate outcome

The gate has only two outcomes:

- `GREEN`: every required non-optional command passes, PostgreSQL integration
  tests run rather than skip, the deployed real-inference probe passes, and no
  release-blocking risk lacks its required evidence.
- `BLOCKED`: any required check fails or cannot run, PostgreSQL or model
  dependencies are unavailable, or a release condition remains unmet.

Do not convert a failure, skip, missing artifact, or undocumented waiver into a
green result. A change to security policy, public behavior, persistence,
queueing, or the frozen inference contract requires a separately approved plan.

## Gate matrix

| Boundary | Required evidence |
|---|---|
| Authentication and ownership | Missing and invalid credentials return the stable `401`; inactive users return `403`; cross-owner single-record access remains the non-disclosing `404`; administrator read behavior remains explicit. |
| Malformed and corrupt input | Missing, empty, invalid, mismatched, unsupported, encoded-oversized, and decoded-pixel-oversized uploads fail with the established safe status and create no prediction or retained object. Legacy stored over-limit inputs fail safely before decode-heavy worker processing. |
| Storage and cleanup | Opaque keys cannot escape the configured root; database or admission failure after storage attempts deletion; cleanup failure is logged without replacing the original error. |
| Admission and queue pressure | Per-user request and outstanding limits plus the global outstanding limit hold at boundaries and under PostgreSQL concurrency. |
| Worker reliability | Claims use `SKIP LOCKED`; retry timing, lease recovery, attempt fencing, commit reconciliation, terminal cleanup, and nondisclosing failure behavior remain intact. |
| Model dependencies | Missing or invalid registry/package state fails closed; selected package identity and public health output reveal no internal paths. |
| Real inference | A disposable deployed stack completes authenticated upload, PostgreSQL queueing, local storage retrieval, selected-package inference, atomic persistence, and owner readback. |
| Migrations | PostgreSQL 16 preserves representative legacy data across Alembic upgrade to head, downgrade to base, and re-upgrade to head in an isolated temporary schema. |
| Repository quality | Pinned dependencies, documentation validation, one Alembic head, changed-Python formatting, full pytest with PostgreSQL 16, Docker Compose configuration, application-image build, and complete diff inspection pass. |

The `w7_production_gate` pytest marker selects the permanent regression suite.
`VDDAI_TEST_POSTGRES_DATABASE_URL` must point to an explicitly disposable
PostgreSQL 16 database. The PostgreSQL tests create UUID-named schemas and drop
only those schemas, but the database must still never be a production target.
`scripts/run_production_gate.py` is the authoritative entry point: it blocks
before pytest when the URL is absent and returns a failed result if any required
PostgreSQL test is missing or skipped. Its required inventory names all seven
current PostgreSQL concurrency and migration tests, while every new test carrying
both gate markers also becomes mandatory. Running the marker directly retains
the canonical suite's optional-PostgreSQL behavior and is not a W7D4 verdict.

## Hosted W8 quality gate and image publication

`.github/workflows/ci.yml` is the authoritative hosted merge-quality gate for
pull requests, `master` pushes, and manual dispatches. It provisions an
ephemeral PostgreSQL 16 service and runs the complete canonical suite without
the default PostgreSQL skips, then runs `scripts/run_production_gate.py` as the
strict W7D4 regression verdict. The same mandatory job validates exact Python,
pip, and requirement pins, documentation, one Alembic head, Black formatting
for Python files added or changed in the Git comparison, and Docker Compose
configuration. A separate mandatory job builds and inspects the immutable
application image without publishing it. Another mandatory job audits the
installed pinned Python environment with `pip-audit==2.10.1`; this is a known
dependency-vulnerability check, not an operating-system image scan, SBOM,
provenance attestation, signing mechanism, or proof of application security.
The audit runs in strict mode and every reported finding blocks the quality
gate. [ADR 0016](../decisions/0016-hs256-jwt-provider-and-strict-audit.md)

The stable aggregate check is `VDDAI v0.1.0 quality gate`. It succeeds only
when every required job reports `success`; failure, skip, cancellation, timeout,
or unavailable evidence remains non-green. The verification, audit, image, and
aggregate jobs retain read-only repository access. Only a push to `master`
after that aggregate succeeds may run the isolated GHCR publication job. It has
only `contents: read` and `packages: write` and uses the GitHub Actions
short-lived `GITHUB_TOKEN`; pull requests and manual dispatches never publish.

The published private image uses a full-source-SHA lookup tag and OCI source,
revision, and version labels. Its returned digest is the authoritative staging
or release identity; never deploy by `latest` or ambient registry discovery.
The image contains application code and pinned runtime dependencies, not the
ignored model registry, package, feature bank, checkpoint, uploads, or other
runtime state. The deployment-oriented `scripts/run_immutable_compose.py`
validates the explicitly supplied digest, then streams the Compose
configuration with those artifacts mounted read-only for API and worker. It
does not provision, deploy, or promote a model.

Hosted CI does not provision ignored registry, package, feature-bank, or model
weight files and does not run the data-creating deployed probe. The deployed
real-inference proof remains environment-specific release evidence. CI success
does not make the full W7D4 release outcome green by itself and never authorizes
merge, release, deployment, or model promotion.

## W8D3 staging environment

ADR 0014 defines the approved staging boundary: one Linux Docker Compose host,
with Caddy as the only public service and a stable HTTPS FQDN. The API and
worker use one explicit GHCR digest and the staging runner also requires exact
digest references for PostgreSQL, Redis, and Caddy. Never substitute a tag,
`latest`, source bind mount, or an ambient image discovery step.

Copy `deploy/staging/staging.env.example` to a permission-restricted location
outside the repository, replace every template credential, and set
`VDDAI_STAGING_ENV_FILE` to that absolute file path. Set the staging FQDN,
approved image digests, and an absolute host path to the already provisioned
artifact snapshot. Authenticate the host Docker client to private GHCR with a
pull-only credential held outside Git. Do not print the environment file or
credentials.

The staging env file supports literal, unquoted printable ASCII values only:
no whitespace, quotes, dollar signs, hash signs, backslashes, interpolation,
inline comments, or duplicate keys. Use full-line comments. Only settings listed
in the template are supported; libpq `PG*` routing overrides are not accepted.
PostgreSQL user and database names must contain only ASCII letters, digits, and
underscores and must not start with a digit. `DATABASE_URL` must exactly match
`postgresql+psycopg://USER:PASSWORD@postgres:5432/DATABASE`, with the same
bootstrap user/database and password. Choose a long random password using only
ASCII letters, digits, and `-._~`; use the identical literal in both settings.
Percent-encoded or other punctuation-bearing passwords are rejected because
the existing Alembic configuration handoff cannot accept percent escapes.
Query parameters, alternate hosts,
ports, and mismatched credentials are rejected before Compose runs. Do not
print real credentials when preparing this URL.

```powershell
$env:VDDAI_STAGING_ENV_FILE = "/etc/vddai/staging.env"
$env:VDDAI_STAGING_FQDN = "staging.example.com"
$env:VDDAI_APPLICATION_IMAGE = "ghcr.io/owner/vddai@sha256:<digest>"
$env:VDDAI_POSTGRES_IMAGE = "docker.io/library/postgres@sha256:<digest>"
$env:VDDAI_REDIS_IMAGE = "docker.io/library/redis@sha256:<digest>"
$env:VDDAI_CADDY_IMAGE = "docker.io/library/caddy@sha256:<digest>"
$env:VDDAI_ARTIFACTS_PATH = "/srv/vddai/artifacts"
python scripts/run_staging_compose.py config --quiet
python scripts/run_staging_compose.py up -d
```

The runner fixes the Compose project name to `vddai-staging`; do not use an
ambient `COMPOSE_PROJECT_NAME` to create a second set of staging volumes. API
readiness requires both `/health` and `/health/model`, so worker and Caddy do
not start until the provisioned production-selected package is valid.

The artifacts directory is mounted read-only and must contain the selected
registry, package, feature bank, and ResNet checkpoint. Confirm the expected
identity through `GET /health/model`; it exposes only the selected model
version and package ID. `GET /health` and `GET /health/db` provide the other
safe readiness interfaces. The W8D4 section below records live HTTPS smoke on the earlier staging revision
and an isolated two-digest application rollback rehearsal. Repeat smoke and
rollback verification for the next approved immutable candidate as required;
never run a data-creating probe without explicit operator approval.

Before a deploy that can migrate schema, stop the worker and take recoverable
backups of PostgreSQL, uploads, and the artifact snapshot. Keep the old image
digest and artifact snapshot until the replacement is accepted. Do not run old
and new worker versions together. A downgrade requires the ADR 0010/0011
preconditions; do not use `docker compose down -v`, which deletes durable
state, without explicit human authorization.

## W8D4 staging smoke and supervised rollback

Use the [staging smoke client](../../scripts/smoke_staging.py) after an operator
approves the HTTPS target and one synthetic prediction. The W7 inference probe
has a separate disposable development and test contract.

### Run the staging smoke

Provision two distinct active non-admin accounts reserved for this gate.
Verify their user IDs and empty prediction histories. Store the exact HTTPS
`origin` and separate `owner` and `other` objects in a permission-restricted JSON
file outside Git. Each object has an integer `id`, `email`, `password`, and
`is_admin: false`. Use a fixed protected state directory outside Git for that
account pair and origin.

Use the approved HTTPS FQDN on the default port with normal certificate and
hostname verification. The client rejects redirects and connects directly.
The CLI options below take precedence over `VDDAI_STAGING_BASE_URL`,
`VDDAI_STAGING_FQDN`, `VDDAI_EXPECTED_MODEL_VERSION`, and
`VDDAI_EXPECTED_PACKAGE_ID`.

```powershell
python scripts/smoke_staging.py `
  --base-url "https://<approved-staging-fqdn>" `
  --expected-fqdn "<approved-staging-fqdn>" `
  --expected-model-version "<approved-registry-model-version>" `
  --expected-package-id "<approved-package-id>" `
  --timeout-seconds 120 `
  --allow-staging-test-data `
  --accounts-file "<absolute-protected-accounts-json>" `
  --state-dir "<absolute-fixed-protected-state-directory>" `
  --evidence-file "<absolute-new-file-outside-repository>"
```

Create the evidence parent directory before starting and use a fresh evidence
filename. The client checks service, database, and exact model identity before
login. It verifies an unauthenticated `401`, binds both logins to the expected
subjects, and requires empty histories. It submits one synthetic PNG and
requires `202` with a queued prediction ID. The second account receives the
same safe `404` for the owner's known prediction and an absent prediction.

The owner polls for real worker completion. The result carries the expected
package, full public-safe lineage, latency, score, threshold, and decision.
Scores strictly above the threshold are anomalous. Equality is normal. The
client verifies the same typed result in a fresh owner read and owner history,
then rechecks health and selection. Queue evidence combines API acceptance
and persisted readback with the PostgreSQL deployment record.
[Reviewed client contract](../reviews/2026-11-21-w8d4-staging-smoke-r4.md).

### Failure reporting and retention

Exit zero requires all smoke stages and a saved receipt. The supervised
deadline includes child startup, network requests, and polling. On failure,
preserve the receipt and its safe stage and error code, model identity, run
ID, known prediction ID, and cleanup status. Treat a timed-out upload as
potentially committed and reconcile it before attempting another upload.
Recovery decisions remain with the operator.

The runner reserves `w8d4-pending` under the fixed state directory before
upload. `run.json` binds the run, origin, model identities, and two accounts.
`prediction.json` records the ID once known. An unresolved reservation blocks
a new upload. Reuse the same accounts and state directory after reconciliation.

Reconcile each run within one business day after terminal settlement. Match
the protected run to the exact accounts, prediction, and object through
operator-only records. If the ID is missing, resolve the ambiguous upload
against PostgreSQL and storage before clearing the reservation. Preserve
redacted readback and cleanup evidence first. With explicit approval for
staging data deletion, remove the confirmed terminal test row, then remove
the now unreferenced object through the validated storage boundary. Keep the
reservation while work is queued, processing, ambiguous, or awaiting
disposal. Record partial cleanup and retry by exact identity. Clear the
reservation after confirmed disposal or proof that the upload created no data.
[Durable image storage](../decisions/0009-durable-image-storage-boundary.md).

### Release record and backups

The 2026-11-26 isolated rehearsal established these immutable application
identities. Confirm current authorization and actual deployment identities
before applying them to a later recovery.

| Role in the rehearsal | Published application image | Source revision |
| --- | --- | --- |
| Current and roll-forward | `ghcr.io/burymewithmykatana/vddai@sha256:488b3f7fe19cb91461357e25e24b0cbadb877814568a33cf71aadebabbe67ae5` | `1b9f6160883361bdb99298b256815197ccab8eba` |
| Previous and rollback | `ghcr.io/burymewithmykatana/vddai@sha256:7becd911afdb0bbcd0dc5c2f8b7f261bea151a7a636dd338f25415ce21a503a8` | `8113c89897c4bc446551f0ec7adf204bae3b8c38` |

The rehearsal restored PostgreSQL 16.16 at Alembic revision `20260821_04`.
Both images started against that revision. The registry selected
`mvtec-tile-resnet18-knn-fe64db2228370b2d-dadb8ca7c9b0`. Predictions persisted
package ID `mvtec-tile-resnet18-knn-fe64db2228370b2d`.
[R6 image, database, and artifact evidence](../reviews/2026-11-26-w8d4-staging-smoke-r6.md).

Record the target, approval, application and dependency digests, source
revisions, Alembic revision, model version and package ID, and backup
checksums in the protected release record. Verify the image of each running
API and worker by exact container ID.

```powershell
python scripts/run_staging_compose.py ps -q api worker
docker inspect --format '{{.Name}} {{.Config.Image}} {{.Image}}' <container-id>
```

Drain accepted work during the maintenance window, confirm queue counts in
PostgreSQL, and stop workers before the API. Preserve the database, uploads,
and complete matching artifact snapshot with the SQLite registry, package
manifest, feature bank, and cached checkpoint. Record checksums and verify the
logical dump catalog and isolated restoration. Take physical volume archives
with PostgreSQL stopped and use a compatible recovery image. Keep an off-host
copy under the operator's backup policy.

The 2026-08-31 Docker Desktop archive documents a local PostgreSQL 16.15
restore from `desktop-linux`. The later server rehearsal verified the database
dump, linked uploaded file, and artifact archive by checksum and restored
them to isolated storage. The records establish same-host backup and restore.
Exact original capture ordering and off-host retention remain unverified.
[R6 backup provenance](../reviews/2026-11-26-w8d4-staging-smoke-r6.md).

### Application rollback and roll-forward

1. Confirm an approved maintenance window, preserved backups, baseline smoke,
   and a completed result reserved for owner readback. Record the exact API
   and worker images. Suspend new ingress while keeping an operator validation
   route available.
2. Confirm that the previous image recognizes the database revision and that
   the revision matches the image's Alembic head. The rehearsal ran
   `alembic current --check-heads` before the normal `alembic upgrade head`
   at API startup. Stop the image transition if compatibility is unresolved.
   A schema downgrade or restoration onto live data requires its own approval
   and the retry, lease, and admission preconditions.
   [Worker reliability ADR](../decisions/0010-database-backed-prediction-reliability.md).
   [Admission ADR](../decisions/0011-database-backed-prediction-admission.md).
3. For an isolated rehearsal, stop the current worker and submit a fresh
   synthetic image through the isolated API. Verify the accepted ID stays
   queued with zero attempts and confirm that no processing jobs remain.
   Preserve the queued job and upload across the switch.
4. For authorized staging recovery, select the exact previous digest in
   `VDDAI_APPLICATION_IMAGE` and validate the Compose config. Stop workers
   before the API, preserve the volumes and registry, and start the
   replacement API first.

   ```powershell
   python scripts/run_staging_compose.py config --quiet
   python scripts/run_staging_compose.py stop worker
   python scripts/run_staging_compose.py stop api
   python scripts/run_staging_compose.py up -d --no-deps api
   ```

   Check the API image, schema, and health endpoints. Start the matching
   worker after those checks succeed.

   ```powershell
   python scripts/run_staging_compose.py up -d --no-deps worker
   python scripts/run_staging_compose.py ps -q api worker
   ```
5. Verify both running images, model identity, and recovery of accepted
   queued work where present. Read the retained completed result as its
   original owner. Run the separately authorized staging smoke with its
   dedicated, reconciled accounts. Retain the phase and validation records.
   Reopen ingress after successful validation.
6. Roll forward with the exact recorded current digest. Repeat the drain,
   compatibility check, worker-first shutdown, and API-first startup.
   Verify both images, retained results, fresh inference, and service,
   database, and model health. Record the outcome and cleanup evidence.

In the tested isolated run, current-image prediction `2` remained readable
with the same result. The previous worker completed queued prediction `3` and
fresh prediction `4`. After roll-forward, reads of all three matched and
current-image prediction `5` completed. The rehearsal used a private network,
disposable PostgreSQL, copies of uploads, and a read-only artifact mount.
The record confirms scoped cleanup and matching live staging container and
registry identities. [R6 phase and cleanup verification](../reviews/2026-11-26-w8d4-staging-smoke-r6.md).

### Model rollback

Staging serving follows the registry's `production` pointer. Inspect the
selection and candidates from a verified read-only snapshot before proposing
a transition. In the verified release snapshot, both environments select the
one version listed above and both `rollback_version` fields are null. Model
rollback stops at target verification until an approved previous selection
is recorded.
[Registry-selected serving ADR](../decisions/0008-registry-selected-production-package.md).

A separately approved transition requires workers stopped before the API and
exclusive registry access. Preserve the existing SQLite registry and
append-only transition history. Use `ModelRegistry.rollback` with
`environment=ModelStage.PRODUCTION`, the identified `requested_by` actor, the
reason, and predeclared `PromotionCriteria`. The service selects the recorded
rollback version, rechecks gates, and returns an audit attempt ID.
[Controlled registry ADR](../decisions/0007-controlled-model-registry.md).

The package-validator callback resolves the exact candidate under the
approved artifact root with `PromotedModelSelection.from_candidate` and loads
it with `load_promoted_model_package`. The smoke callback runs
`AnomalyInferenceService(package=package).predict` on a synthetic image and
returns `SmokeInferenceEvidence` with the actual package ID, score, threshold,
and label. Record the attempt ID and resulting selection. Use the approved
artifact snapshot read-only for serving. Restart the API first, verify
selection, start the worker, and run the separately authorized smoke gate.
A rejected transition preserves the existing selection. To roll forward the
model, repeat the separately approved procedure using the registry's
then-recorded rollback selection and revalidate.

### W8D4 acceptance evidence

| Original criterion | Evidence |
| --- | --- |
| Run health, auth, upload, queue, inference, persistence, and result-read smoke checks after deploy | All seven automated stages passed on live staging HTTPS. The review binds the result to owner-scoped PostgreSQL state and the active package. [R5](../reviews/2026-11-21-w8d4-staging-smoke-r5.md). |
| Define rollback to the previous application and model versions | The recorded digest pair, compatible schema, and guarded model procedure identify their required inputs. The verified registry has no previous model target. |
| Perform and document one rollback rehearsal | The isolated application rehearsal verified same-job recovery, owner readback, roll-forward, archive checks, and scoped cleanup. [R6](../reviews/2026-11-26-w8d4-staging-smoke-r6.md). |
| Supply automated smoke and a tested rollback procedure | R5 records the execution of the staging client. R6 records the later isolated application procedure and verification of the exact reviewed subject. |
| Finish with tests, documentation, and a visible commit | Independent QA `W8D4-QA-2026-11-26-001` passed 105 focused, 507 canonical, and 171 strict PostgreSQL tests. This guide is the documentation delta. The visible commit and merge require human approval. |

The November operational release record uses run
`vddai-w8d4-rh-20261126144150z`. R6 identifies the execution ledger, digests, and
cleanup receipt. [Original W8D4 task](https://app.notion.com/p/3ac0ab50ef678177a31ed823994298a9).

## W9D1 prediction lifecycle logs

The API and worker emit one JSON object per lifecycle event on standard
output. Operators can follow a prediction from upload through queueing,
inference, result persistence, and authorized readback.

| Field | Meaning |
| --- | --- |
| `schema_version`, `timestamp`, `level` | Schema version `1`, a UTC timestamp, and log severity. |
| `service`, `event`, `status` | The API or worker, the lifecycle event, and its outcome or recorded prediction state. |
| `request_id` | A server-generated ID for each HTTP request. Events on one API request share this ID. Worker events have a null request ID. |
| `prediction_id`, `job_id`, `attempt` | Once known, both IDs carry the same PostgreSQL prediction ID. Worker attempts use the persisted attempt number. |
| `model_version` | The serving package ID stored with a result. The selected registry version is reported by `GET /health/model`. |
| `latency_ms` | Stage duration in milliseconds when available. Successful inference uses the latency recorded with the result. |
| `method`, `route`, `http_status`, `error_code` | Bounded HTTP metadata, the registered route template, and the stable diagnostic code when available. |

Fields appear as null when they are unavailable. Request headers, bodies,
raw URLs, image object keys, and exception details stay outside the event
schema. A denied or missing prediction read records the HTTP `404` with the
route template and no prediction ID. On either service's normal entry point,
an application initialization error during import emits
`service.startup_failed` with `startup_failed` and exits with status `1`.

### Follow one prediction

Locate the upload in the API logs and use its `request_id` to find
`prediction.enqueue`. Use the resulting `job_id` across the API and worker
logs. The example uses synthetic identifiers and a fixture package ID.

| Event | What to look for |
| --- | --- |
| `storage.write_finished` | Upload request `d25815019f0c47628e2a6a4b2112b671` stored an image. |
| `prediction.enqueue` | The same request committed job `42` in state `queued`. |
| `http.request_finished` | The upload request finished with `202` for `POST /predictions`. |
| `prediction.claim` | The worker committed the claim for job `42`, attempt `1`. |
| `storage.read_finished` | The worker read the image for job `42`. |
| `prediction.inference` | Attempt `1` scored with fixture package `mvtec-tile-resnet18-knn-a6378e04c6442353`. |
| `prediction.terminal_committed` | The worker committed the completed result and package identity. |
| `prediction.readback` | Authorized request `09bed4bac54149caacc2fda01408f106` retrieved job `42` and its package identity. |
| `http.request_finished` | The readback request finished with `200` for `GET /predictions/{prediction_id}`. |

Use `attempt` to follow retry and recovery events. A committed retry emits
`prediction.retry_scheduled` with status `processing`. A fenced completion
emits `prediction.attempt_discarded`. If a result commit reports an error,
`prediction.result_observed` records that the worker subsequently read a
durable terminal result for the same attempt. The corresponding
`prediction.settlement_failed` records the reported persistence error.
An upload whose queue commit fails may also produce a
`storage.orphan_cleanup` event on the upload's request ID.

W9D1 review evidence is available in the
[independent re-review](../reviews/2026-11-27-w9d1-correlated-logging-r2.md).

## W9D2 service and queue metrics

The API and worker each serve a private Prometheus registry when
`METRICS_ENABLED=true`. The default is `false`. With
`METRICS_BIND_MODE=loopback` (the default), the listeners bind to
`127.0.0.1`. The default ports are `9108` for the API
(`METRICS_API_PORT`) and `9109` for the worker (`METRICS_WORKER_PORT`).
An operator on the same host can check an enabled loopback listener with
`curl http://127.0.0.1:9108/metrics` or
`curl http://127.0.0.1:9109/metrics`. The application’s public API
`/metrics` path continues to return `404`.

The `container` bind mode resolves the process hostname and requires one
IPv4 address in the private `10/8`, `172.16/12`, or `192.168/16` ranges.
Keep that listener reachable only on the approved internal network. These
listeners use HTTP and rely on network isolation for access control.
Listener startup errors produce the safe `service.metrics_unavailable`
diagnostic. The API or worker can continue running while its metrics are
unavailable. Treat an unreachable listener as missing telemetry and check the
service health separately. See
[ADR 0015](../decisions/0015-private-observability.md) for the boundary.

| Listener | Metric | Interpretation |
| --- | --- | --- |
| API | `vddai_api_ready` | The API completed startup. |
| API | `vddai_http_requests_total`, `vddai_http_request_duration_seconds` | Request counts and duration by bounded method, registered route template, and HTTP status class. Unmatched routes share one label and unfinished responses count as `5xx`. |
| API | `vddai_database_ready`, `vddai_queue_depth`, `vddai_queue_oldest_age_seconds` | A successful read reports depth and seconds since the oldest acceptance for `queued`, `active`, and `retry_waiting`. Active includes expired claims awaiting recovery. Empty states have zero depth and age. A DB error reports readiness zero and omits queue values. An overlapping snapshot omits the database and queue metrics for that scrape. |
| Worker | `vddai_worker_ready`, `vddai_worker_model_ready` | Worker readiness reflects the latest recovery and claim poll. Model readiness is unknown (`NaN`) before an observed model initialization failure or successful inference. |
| Worker | `vddai_job_claims_total`, `vddai_job_retries_scheduled_total`, `vddai_job_terminal_total` | Counts of committed claims, retry schedules, and observed terminal commits. |
| Worker | `vddai_job_duration_seconds`, `vddai_inference_duration_seconds` | Histograms for acceptance through acknowledged terminal commit and successful inference using its frozen latency boundary. A terminal result found after an ambiguous commit does not create a duration sample or increment the terminal counter. |
| Worker | `vddai_job_execution_failures_total` | Failed attempts by bounded stage (`model`, `storage`, or `inference`). Use terminal job status to count failed jobs. |

The API collects queue state with one grouped read query. PostgreSQL applies a
one second statement timeout to this snapshot. Metrics are process local and
counters reset on restart. Labels and diagnostics exclude user identifiers,
job identifiers, raw URLs, uploaded image content, and secrets.

Pilot targets are p95 API latency at most **1 second**, p95 latency from job
acceptance through terminal commit at most **15 seconds**, p95 inference
latency at most **5 seconds**, and unexpected failures at most **1%**.
Assess those targets from an explicit workload. The W9D2
[independent re-review](../reviews/2026-11-27-w9d2-service-metrics-r2.md)
and `W9D2-QA-2026-11-27-001` verify the signals and their failure behavior.

## W9D3 input and model quality

The private API listener reports committed uploads through
`vddai_upload_accepted_total` and original width and height through
`vddai_upload_dimension_pixels`. It counts image validation rejections in
`vddai_upload_validation_rejected_total` by bounded status. Queue rollback
leaves the accepted upload count unchanged.

The private worker listener summarizes successful inference attempts in the
current and previous 59 minute buckets. It records image format, original
width and height, the mean and standard deviation of normalized RGB pixels,
anomaly score bins, anomaly rate, and the observed package ID. The observer
runs after inference measures its latency. A retry can produce another
observation if it also scores successfully. Only bin counts and sums remain
in memory. The monitor discards expired buckets and retains no images,
paths, prediction identifiers, or individual scores.

### Build the reference

Run the offline builder with an explicit frozen package, its training feature
bank, the matching canonical dataset manifest, and the local dataset root.
Use the existing local `TORCH_HOME` cache for the frozen ResNet-18 weights.

```powershell
python -m ml.build_quality_reference `
  --package-manifest "<package>/run_manifest.json" `
  --feature-bank "<feature-bank-directory>" `
  --dataset-manifest "<dataset-manifest.json>" `
  --dataset-root "<dataset-root>" |
  Set-Content -Encoding utf8 "<private-directory>/quality-reference.json"
```

Keep the generated aggregate JSON outside Git. The builder checks the package
and manifest fingerprint, rejects duplicate sample IDs and canonical image
paths across splits, and compares decoded format, size, and mode to each
normal validation record. It reads image bytes only from the matched normal
validation split. The reference is specific to its package, dataset manifest,
and preprocessing version. The manifest fingerprints its recorded metadata.

Set `METRICS_QUALITY_REFERENCE_FILE` to the reference path readable by the
worker when enabling private metrics. Synthetic fixture references are
accepted only with `ENVIRONMENT=test`. A comparison requires at least 30
matched reference observations and 30 observations from the current window.
A missing, invalid, mismatched, or mixed window has
`vddai_quality_comparison_ready=0` and emits no warning samples. The monitor
waits for the older model's observation bucket to expire before comparing
after a switch. `vddai_quality_reference_count` identifies the loaded
reference source and its count.

### Interpret a shift

| Signal | Warning when comparison is ready |
| --- | --- |
| `pixel_mean` | Mean normalized RGB level differs from the reference by at least 0.15. |
| `pixel_contrast` | Average per-image RGB standard deviation differs by at least 0.10. |
| `format_mix` | A format's share differs by at least 20 percentage points. |
| `anomaly_rate` | The anomaly label rate differs by at least 20 percentage points. |
| `score_p95` | The nearest-rank 95th percentile exceeds 1.5 times the reference p95. |

Use `vddai_quality_shift_warning{signal="..."}` or capture one private
worker scrape and summarize it locally:

```powershell
curl.exe --fail --silent http://127.0.0.1:9109/metrics --output "<private-directory>/worker-metrics.txt"
python -m scripts.report_quality_shift "<private-directory>/worker-metrics.txt"
```

A report with an available comparison and an empty warning list indicates
the thresholds were clear. The report uses `warnings: null` when comparison
is unavailable. These provisional warnings describe aggregate change. Start
by checking the sample count, package identity, and upload mix. The serving
classifier and its approved threshold continue to govern predictions.

The local frozen package `mvtec-tile-resnet18-knn-fe64db2228370b2d` produced
a 46-image matched reference. The controlled validation replay produced no
warnings, while 30 shifted synthetic JPEG observations triggered all five.
See the [independent re-review](../reviews/2026-11-27-w9d3-quality-monitoring-r2.md)
for the reviewed subject and closure evidence.

Independent QA `W9D3-QA-2026-11-27-001` matched the frozen reference
and verified the private scrape, rollback, and report behavior.

## W9D5 local pilot capacity

The disposable workload uses two authenticated synthetic owners and one
outstanding client job. It schedules 10 jobs in a five-minute warmup and 60 in
a fifteen-minute steady phase. The steady rate is four jobs per minute total,
two per owner. It cycles PNG, JPEG, and WebP at 384 × 288, 640 × 480, and
1024 × 768 pixels. Each job has a 15-second deadline shared across upload and
owner readback. The runner requires a distinct queued prediction for every
accepted upload. [Local runner instructions](../../readme.md#w9d5-local-pilot-soak)

### Measured results

The 28 November 2026 run used one API, one worker, PostgreSQL, Redis, and
private Prometheus and Grafana in a local Docker environment with 8 vCPUs and
3.76 GiB of memory. The worker used the frozen package
`mvtec-tile-resnet18-knn-fe64db2228370b2d`.

| Metric | Observed | Limit |
| --- | --- | --- |
| API request p95, 374 samples | 0.110 s | ≤ 1 s |
| Client submission to observed terminal result p95 | 1.584 s | ≤ 15 s |
| Persisted inference p95 | 0.175 s | ≤ 5 s |
| Unexpected failures | 0 of 70 (0%) | ≤ 1% |

The workload lasted 1,200.147 seconds and completed all 70 jobs. PostgreSQL
confirmed 71 distinct completed rows including one separate preflight
prediction. All completed in one attempt. The queue drained. At 15-second
scrapes, the observed maxima were one queued job, one active job, and zero
waiting retries.

| Service | Peak sampled CPU | Peak sampled memory |
| --- | --- | --- |
| API | 69.95% | 542.6 MiB |
| Worker | 18.94% | 442.1 MiB |
| PostgreSQL | 29.08% | 44.36 MiB |
| Redis | 9.26% | 15.25 MiB |
| Prometheus | 2.41% | 52.48 MiB |
| Grafana | 17.10% | 552.1 MiB |

Each service had 70 successful resource samples. Individual service peaks can
occur at different times. The receipt ties the results, application image,
package, SQL counts, and fixture cleanup to the exact runner. Its SHA-256 is
`9a45c0acad346a6860f222237e197d1122413a9618ef45f5a3eede1b38afb146`.
Independent QA `W9D5-QA-2026-11-28-001` verified the receipt and passed 476
canonical and 172 strict PostgreSQL tests with zero skips. [Independent re-review](../reviews/2026-11-28-w9d5-local-pilot-soak-r2.md)

### Capacity and release gate

The verified local envelope is four steady jobs per minute with one
outstanding client job on the measured stack and package. End-to-end latency
was the largest measured delay. It includes API handling, queue wait,
inference, persistence, and client polling. The available aggregates establish
the local budget and leave phase-by-phase attribution and saturation open.
Keep optimization deferred until that profiling is justified by measurements.
The staging workload remains a separate, human-authorized release gate on an
immutable candidate.

## Required commands

From the repository root:

```powershell
$env:VDDAI_TEST_POSTGRES_DATABASE_URL = "<disposable-postgresql-16-url>"
python scripts/run_production_gate.py
python -m pytest -q app/tests/test_prove_real_inference.py
python scripts/validate_docs.py
.\scripts\verify.ps1 -IncludeFormatting -IncludeDockerConfig
```

With a disposable Docker stack and the selected package, feature bank, and
ResNet-18 checkpoint provisioned:

```powershell
docker compose up --build -d
docker compose ps
docker compose exec api python scripts/prove_real_inference.py
docker compose logs --tail=200 api
docker compose logs --tail=200 worker
```

When teardown is required, use `docker compose down`. Do not append `-v`
without explicit human authorization because it deletes local Docker volumes.

## Risk register

| ID | Risk and current boundary | Owner | Severity | Release condition and evidence |
|---|---|---|---|---|
| `W7-R01` | `JWT_SECRET_KEY` has a development placeholder default. | Platform / Security | Release blocker | Every nonlocal environment must inject a unique secret. Configuration evidence must confirm the placeholder is absent without printing the secret. Changing application startup policy requires human security approval. |
| `W7-R02` | Multipart receipt and temporary spooling occur before route-level bounded reads and authenticated prediction rate admission. | Platform | Release blocker for network exposure | Enforce request-body and temporary-storage limits at the ingress/runtime layer before exposing the pilot to untrusted networks; retain the application maximum-plus-one test evidence. |
| `W7-R03` | The configured image store is local filesystem storage. | Platform | Conditional release blocker | Limit the pilot to one host with a shared API/worker filesystem. A multi-instance deployment requires a separately approved shared object-store implementation. |
| `W7-R04` | Input retention follows prediction-history lifetime; no automated retention scheduler or public delete flow exists. | Product / Platform | Release blocker before customer images | Approve an operator-owned retention and deletion procedure before accepting customer data. Automated retention remains out of W7D4 scope. |
| `W7-R05` | Registry, feature-bank, threshold, and ResNet-18 weight files are provisioned runtime dependencies outside Git. | ML / Platform | Release blocker | The exact promoted selection and all checksummed artifacts must be present, and the deployed proof must pass without download or fallback. Promotion remains human-approved. |
| `W7-R06` | Downgrade removes retry/lease and admission state introduced by W7D2/W7D3. | Platform / Database | Release blocker for rollback | Stop all workers, confirm no processing row depends on recovery metadata, back up the target, and obtain human rollback approval. The gate exercises downgrade only in its isolated schema. |
| `W7-R07` | The deployed probe creates two users, a prediction row, and an input object and intentionally does not perform record-coupled cleanup. | QA / Platform | Operational | Run only against a disposable environment identified by `/health` as `development` or `test`, and record its target identity. Every other identity fails closed before data creation. |
| `W7-R08` | Automated alerting and production dashboards are scheduled after Week 7. | Platform | Conditional release blocker | Do not operate an unattended pilot until the later monitoring gate supplies alerts, dashboards, and an operator runbook. A supervised local pilot must record this limitation. |

## Evidence record

The Coder records exact commands, pass/skip/fail counts, PostgreSQL version,
test-schema isolation, package ID, changed files, and Git range. The independent
Reviewer records findings in a new immutable report under `docs/reviews/`. QA
then reruns the approved subject and maps evidence to every W7D4 criterion.
Documentation may update this current document only after eligible review and
QA evidence. Deployment and merge remain explicit human gates.
