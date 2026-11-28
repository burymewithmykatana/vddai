# Pilot monitoring runbook

- Status: Current
- Scope: W9D4 local VDDAI pilot monitoring

## Start a local monitoring session

Use a disposable local checkout with a configured development `.env`,
local artifacts, Docker Compose, and a free loopback port 3000. Set
`VDDAI_GRAFANA_PASSWORD_FILE` to an absolute path outside Git. Use a
nonempty operator owned password file that the Grafana container can read.
Grafana uses that file on initial database setup. Subsequent starts use the
stored Grafana account. Keep the file available to Compose while the overlay
is in use.

For sessions that use quality comparisons, [build a W9D3 reference](production-readiness.md#build-the-reference)
for the approved package. Save the generated aggregate in the checkout at
`artifacts/evaluations/monitoring/quality-reference.json`, an ignored path.
The development Compose mount makes the checkout available at `/app`.
Add this container path to the disposable checkout's `.env` before startup:

```dotenv
METRICS_QUALITY_REFERENCE_FILE=/app/artifacts/evaluations/monitoring/quality-reference.json
```

Make the file readable by the worker. The worker reads it at startup. For a
session without quality comparisons, omit the setting. Service and queue
monitoring remain available.

From the repository root, validate the overlay before starting the local
stack:

```powershell
docker compose -f docker-compose.yaml -f deploy/monitoring/compose.yaml config --quiet
docker compose -f docker-compose.yaml -f deploy/monitoring/compose.yaml up -d
docker compose -f docker-compose.yaml -f deploy/monitoring/compose.yaml ps
```

Open Grafana at `http://127.0.0.1:3000/d/vddai-overview` and sign in as
`admin` with the configured password. The dashboard and data source are
provisioned from the repository. The API exporter at `api:9108`, worker
exporter at `worker:9109`, and Prometheus at `prometheus:9090` are reached
within the Compose network. The overlay publishes only the Grafana loopback
port for monitoring. It uses the [private metrics boundary](../decisions/0015-private-observability.md).

Prometheus scrapes every 15 seconds with a three second timeout and stores
aggregate samples with a seven day time retention policy. Grafana stores
local user and dashboard settings in its own volume. The alert rules are
evaluated by Prometheus. Use Grafana Explore with the provisioned
`VDDAI Prometheus` source and `ALERTS{alertstate="firing"}` to see firing
alerts. The overlay has no external notification receiver, so an operator
must watch alerts during use.

### Capture and check the worker quality report

Run these commands in PowerShell 7 from the local Compose checkout with the
same project settings used for startup. The first command reaches
`worker:9109` inside Compose and saves one aggregate snapshot locally.

```powershell
$snapshot = Join-Path ([System.IO.Path]::GetTempPath()) ("vddai-worker-" + [guid]::NewGuid() + ".prom")
$samples = docker compose -f docker-compose.yaml -f deploy/monitoring/compose.yaml exec -T worker python -c 'from urllib.request import urlopen; print(urlopen("http://worker:9109/metrics", timeout=4).read().decode("utf-8"), end="")'
if ($LASTEXITCODE -ne 0) { throw "Private worker scrape failed." }
$samples | Set-Content -LiteralPath $snapshot -Encoding utf8NoBOM
python -m scripts.report_quality_shift $snapshot
```

Confirm the report lists the expected package and a `normal_validation`
reference with at least 30 samples. After at least 30 successful inference
observations for the matching package in the current window, a comparable
window reports `comparison: available`. An empty warnings list means the
thresholds are clear. A missing, invalid, or mismatched reference, a mixed
window, or insufficient observations reports `comparison: unavailable` and
`warnings: null`. Check the reference and observation count before treating
the absence of a quality alert as evidence. The worker metrics port stays
private throughout this procedure.

Use the same Compose file pair to stop the disposable local services and
retain their volumes:

```powershell
docker compose -f docker-compose.yaml -f deploy/monitoring/compose.yaml stop
```

The existing staging launcher has its own deployment contract. Approval of
the local overlay does not apply it to the staging project.

## First response

Record UTC onset, affected target, active application digest, approved model
identity, and the relevant dashboard time range. Save only redacted evidence.
Use the [structured logs](production-readiness.md#w9d1-prediction-lifecycle-logs) to
follow a single request or job and the
[metrics guide](production-readiness.md#w9d2-service-and-queue-metrics) to
interpret queue and worker signals.

### API unavailable

`VDDAIApiUnavailable` fires after one minute of target failure, missing
scrape target, or unavailable startup readiness. Platform checks the normal
`/health` route, then compares ingress and API health against the private
exporter state. If HTTPS health works, check the private listener and
`service.metrics_unavailable` before considering an application rollback.
If a release caused the outage, follow [application rollback](#application-rollback).

### Worker unavailable

`VDDAIWorkerUnavailable` fires after one minute of worker target or poll
failure. Platform checks worker startup, recovery and claim diagnostics,
queue depth, and database readiness. Preserve queued work. If a worker
image regression is confirmed, use [application rollback](#application-rollback)
with workers stopped before switching digests.

### Database unavailable

`VDDAIDatabaseUnavailable` fires when the API is scrapeable and its queue
snapshot stays unavailable for one minute. Platform compares `/health/db`
with database readiness and checks PostgreSQL connectivity, locks, and
storage. One overlapping scrape may omit the snapshot. Fix database
availability before restarting claims. Treat restore and schema operations
as separately approved recovery steps under
[ADR 0014](../decisions/0014-single-host-staging-environment.md).

### Model unavailable

`VDDAIModelUnavailable` fires after one minute of observed model
unavailability. The ML owner checks `/health/model`, the worker's
`model_unavailable` events, and the currently selected package's artifact
integrity and compatibility. Before the first model event the worker gauge
is unknown. Restore the same approved artifacts if they are missing. A model
rollback requires a valid approved target and the
[model rollback checks](#model-rollback).

### Sustained API errors

`VDDAIApiErrors` fires when the five minute `5xx` fraction stays at or
above 2% for five minutes with at least 20 requests in the measurement
window. Platform correlates affected route templates and request IDs,
checks dependency health, and compares the timing with the release. If the
application digest caused the errors, use [application rollback](#application-rollback).

### Queue backlog

`VDDAIQueueBacklog` fires when the oldest queued or retry waiting job
stays older than 30 seconds for five minutes. Platform checks depth,
recovery, worker readiness, inference duration, and admission rejections.
Pause the synthetic producer if it is driving the backlog. Let the existing
claim and recovery logic drain work. Use [application rollback](#application-rollback)
only when evidence connects the backlog to the release.

### Failed inference

`VDDAITerminalFailures` fires after one minute with an estimated three or
more failed terminal jobs in the preceding ten minutes. Platform separates
terminal failures from retried execution attempts. Follow the job ID to
the observed model, storage, or inference diagnostic. Repair the confirmed
dependency or use the approved [application](#application-rollback) or
[model rollback](#model-rollback) procedure for a verified release regression.

### Inference latency

`VDDAIInferenceSlow` fires when the five minute inference p95 estimate
stays above five seconds for five minutes with at least 20 observations.
The ML owner checks inference time beside queue and commit latency, worker
resource contention, and the exact package. If a release regression is
confirmed, use the appropriate [application](#application-rollback) or
[model rollback](#model-rollback) procedure.

### Input quality shift

`VDDAIInputQualityShift` fires after a matched mean, contrast, or format
warning persists for five minutes. The ML owner checks the observation
count, upload rejection and format trends, and the
[private worker quality report](#capture-and-check-the-worker-quality-report).
Confirm the source or capture setting before changing serving behavior.
If a recent ingestion release caused the shift, consider
[application rollback](#application-rollback) after reproducing the issue.

### Model quality shift

`VDDAIModelQualityShift` fires after a matched anomaly-rate or score-p95
warning persists for five minutes. The ML owner compares the current
package, input mix, and [private worker quality report](#capture-and-check-the-worker-quality-report),
and requests human review of
results. Treat a shift warning as a reason to investigate. A verified model
regression can proceed to [model rollback](#model-rollback) only with approval.

## Recovery boundaries

### Application rollback

Identify the exact previously verified application digest and confirm it can
use the current database schema and preserved artifact snapshot. Obtain
operator approval. Stop workers before changing the API or worker image and
preserve a PostgreSQL backup, uploaded objects, and model artifacts. Bring
up the compatible API digest and confirm health before starting the matching
worker. Validate an authorized smoke run, queued-job recovery, retained
owner readback, and private metrics where enabled. A schema downgrade,
restore, or roll-forward follows its own compatibility checks and approved
procedure. See [ADR 0014](../decisions/0014-single-host-staging-environment.md).

### Model rollback

Read the controlled registry and confirm an approved previous package exists
for the target environment. Preserve its checksums and the current artifact
snapshot. Stop if the rollback target is absent. Selection changes require
explicit human approval under
[ADR 0007](../decisions/0007-controlled-model-registry.md) and
[ADR 0008](../decisions/0008-registry-selected-production-package.md).
Validate model health, frozen inference and persisted package identity before
using a reference built for the selected package.

## Validate the configuration

With the pinned Prometheus 3.16.0 `promtool` on the path, run from the
repository root:

```powershell
promtool check config deploy/monitoring/prometheus/prometheus.yml
promtool test rules deploy/monitoring/prometheus/alerts.test.yml
```
