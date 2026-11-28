# W9D4 alert rules, dashboard, and runbook review

## 1. Reviewed subject

Review `W9D4-REV-2026-11-27-001`, 27 November 2026. Independent review of
`codex/w9d4-monitoring-runbook` in the W9D4 worktree. The approved parent and
`HEAD` are `814cdc4da39431526ff381e4ee54318ced7824c0`. The merge base with
`origin/master` is `1b9f6160883361bdb99298b256815197ccab8eba`.
The task-relative committed and staged ranges are empty. Seven overlay and
monitoring assets and three documentation files form the exact reviewed
subject. This review record is independent audit evidence.

| Reviewed file | SHA-256 |
| --- | --- |
| `deploy/monitoring/compose.yaml` | `2d488d3918b0b7164f5050110652c64800064d70349dbe8e3586edd339060566` |
| `deploy/monitoring/grafana/dashboards/overview.json` | `7e3f4c630d6f6cdf855bdda1c3e0729974748bc74417f05551aa273524ed1cb8` |
| `deploy/monitoring/grafana/provisioning/dashboards/pilot.yml` | `5830ca37e403fbb9d242a5eb68af86220431c3ac96baa2f71cf2034153d30e5e` |
| `deploy/monitoring/grafana/provisioning/datasources/prometheus.yml` | `ceb05ee7fd29ada16a9f135ba8d1e6d05dd46a08389d4b145996faad7f80ef4a` |
| `deploy/monitoring/prometheus/alerts.test.yml` | `73e567e46f6fda483d6429b07e3fa236616bf4b7de90d85f73762bc827a2bb8a` |
| `deploy/monitoring/prometheus/alerts.yml` | `83371ba1330cc92821e6702cef439e25d0d046fed6771fe5b565b5f43d1e35c4` |
| `deploy/monitoring/prometheus/prometheus.yml` | `60460ad8bdb6dc8c01a8092e90d9dd4a986da2582781de8369872721cc6fd20d` |
| `docs/catalog.yaml` | `6b9194ac3fad27d851a45495f24bf132a922e6ce682c40eea8a20d78e058d37e` |
| `docs/engineering/monitoring-runbook.md` | `3466cffa5038344cae59e7d3bebb51aca0fbe95da48dc04873d971e92dd92aca` |
| `docs/engineering/README.md` | `49069c1123a640aca06a4d59e247b314e04dc5ddfb7249383dea5e71742736db` |

## 2. Contract and acceptance criteria

The approved [W9D4 task](https://app.notion.com/p/3ac0ab50ef6781eab479cfde7bfbd3a1)
requires a compact operational dashboard, actionable service and queue
alerts, and first-response and rollback instructions. The approved plan also
includes the input and model quality warnings from W9D3. The opt-in overlay
uses pinned Prometheus 3.16.0 and Grafana 13.3.2, seven-day aggregate metrics
retention, loopback Grafana with a protected password file, and private
Prometheus and application exporters. Operators view local rule state.
External alert delivery and staging rollout require separate scope.

The [repository rules](../../AGENTS.md), the
[workflow](../engineering/agent-workflow.md), and the accepted
[staging](../decisions/0014-single-host-staging-environment.md) and
[private metrics](../decisions/0015-private-observability.md) decisions
apply. The established [W9D2 service metrics](../engineering/production-readiness.md#w9d2-service-and-queue-metrics)
and [W9D3 reference and report](../engineering/production-readiness.md#w9d3-input-and-model-quality)
contracts define the metric names and quality readiness conditions.

## 3. Verdict

**CHANGES REQUIRED.** The monitoring configuration, alert rules, and
dashboard PromQL checks passed. The operator runbook misses the reference
setup for quality alerts and points to a host capture address unavailable
in the approved Compose topology.

## 4. Findings

### `VDDAI-REV-001` The setup path omits the matched quality reference

**MEDIUM - OPEN.** `docs/engineering/monitoring-runbook.md` lines 6-38 and
`deploy/monitoring/compose.yaml` lines 8-12.

The setup lists the development environment, artifacts, and Grafana password
file. It never states that the worker needs a readable matched reference or
shows how to configure it for this overlay. The merged configuration using a
development environment with the documented minimal inputs enables the
exporter and leaves `METRICS_QUALITY_REFERENCE_FILE` unset. The worker then
reports `vddai_quality_comparison_ready=0`, and both quality alerts suppress
warnings. The current runbook can lead an operator to a healthy dashboard
while quality comparison remains unavailable for the entire session.

Document how to make a W9D3 reference for the approved package visible to the
worker, which path belongs in the local development configuration, and how to
interpret and verify readiness. Preserve optional behavior for sessions that
explicitly run without a reference. Closure requires the documented Compose
setup with a mounted matched reference, ready after sufficient qualified
observations, and a missing or mismatched reference shown as unavailable.

### `VDDAI-REV-002` The quality incident capture points to a host-only listener

**MEDIUM - OPEN.** `docs/engineering/monitoring-runbook.md` lines 25-30 and
131-147, [inherited report instructions](../engineering/production-readiness.md#interpret-a-shift),
and `deploy/monitoring/compose.yaml` lines 8-12.

The runbook points the incident operator to the inherited report steps.
Those steps capture from `127.0.0.1:9109` on the host. In the approved overlay
the worker binds to its container address and port 9109 has no host mapping.
The supported private endpoint is `worker:9109` within the Compose network.
The inherited capture command cannot retrieve that endpoint from the host.

Document a private in-Compose one-snapshot capture and invocation of the
existing shift report on the resulting local file. Closure requires the
documented command to capture and summarize a private worker scrape in a
disposable overlay session while the host still has no worker metrics
mapping. An empty or unavailable comparison should remain distinguishable
from a matched comparison with clear thresholds.

## 5. Acceptance coverage

| Criterion | Evidence and result |
| --- | --- |
| Compact dashboard for API, worker, PostgreSQL, queue, model, and quality | Twelve provisioned panels and twenty PromQL expressions were inspected. Pinned promtool accepted every expression. Coder native checks verified protected Grafana, datasource health, and a live panel value. |
| Sustained availability, errors, backlog, terminal failure, latency, and matched quality alerts | Pinned promtool found all ten rules and passed the supplied rule tests. An alert for each incident has an owner, severity, and a matching runbook anchor. Quality alert conditions correctly suppress unavailable comparisons. |
| Private opt-in access, protected password, and seven-day retention | Independent merged Compose inspection found one monitoring host binding at `127.0.0.1:3000` and both exporters and Prometheus on the Compose network. Pinned images and password-file binding are present. Coder native runtime confirmed seven-day retention. |
| Actionable first response and rollback | The runbook covers checks, response owners, and separate application and model approval boundaries. The initial matched reference and private quality capture remain open under `VDDAI-REV-001` and `VDDAI-REV-002`. |

## 6. Checks run

- Git branch, base, empty index, merge base, `git diff --check`, and exact
  SHA-256 verification.
- Created a disposable `git archive --format=tar HEAD` snapshot with all
  ten reviewed files overlaid and hash-checked, a synthetic development
  environment, and a separate dummy Grafana password file. The child
  commands inherited no `GIT_*` or `COMPOSE_*` overrides.
- Ran `docker compose -f docker-compose.yaml -f deploy/monitoring/compose.yaml
  config --quiet` and inspected the synthetic local `config --format json`.
  Verified only the Grafana monitoring host port, daemon-internal address
  modes and network membership, the protected password-file binding, and
  absence of the quality reference in the runbook's minimal setup.
- Pinned `promtool 3.16.0` passed `check config
  deploy/monitoring/prometheus/prometheus.yml` with ten rules and `test rules
  deploy/monitoring/prometheus/alerts.test.yml`. A separately generated
  empty-series syntax fixture passed all twenty dashboard expressions.
  Every rule annotation resolved to a distinct existing runbook heading.
- Coder canonical verification recorded **450 passed** on disposable
  PostgreSQL 16.15 and passed base Compose configuration. Native
  Prometheus and Grafana evidence used the exact repository monitoring
  assets with local scrape endpoint adaptation, loaded ten rules and
  twelve panels, returned anonymous HTTP 401, and reached a provisioned
  datasource and API panel. That run is corroborating Coder evidence.
- The Coder reported the separate disposable Docker proof in progress. The
  digest-matched monitoring images were verified and PostgreSQL, Redis, and
  the monitor containers were running. The API was still in startup health
  checks. The end-to-end Docker result is pending.

## 7. Checks deferred

Independent container startup and incident-path verification are QA work
on an eligible remediated range. Live staging and external delivery sit
outside this local review.

## 8. Remediation handoff

1. Obtain human selection of `VDDAI-REV-001` and `VDDAI-REV-002`.
2. Complete the documented matched-reference and private capture paths
   and execute both closure checks in the disposable local topology.
3. Submit exact evidence and the updated range for numbered re-review.
   Preserve this report. QA follows an eligible verdict.

## 9. Residual context

Prometheus evaluates alert conditions and holds local firing state. The
operator watches that state during the local session. Runtime proof using
synthetic data applies to the disposable environment and the reviewed
assets. A staging rollout or registry change remains a separate human
decision.

## Process-learning evidence

| Field | Record |
| --- | --- |
| Observation | The merged monitoring topology gave the worker a correct private endpoint. The previously documented standalone scrape address remained different from that endpoint. |
| Evidence | `VDDAI-REV-002` and the independent Compose projection. |
| Impact | Operator diagnostics need to follow the actual runtime topology. |
| Recurrence | First observed in monitoring overlay review. |
| Candidate improvement | Exercise the exact documented setup and incident commands in the selected topology when verifying an operator runbook. |
| Authority note | This evidence confers no authority to change the workflow or its skills. |
