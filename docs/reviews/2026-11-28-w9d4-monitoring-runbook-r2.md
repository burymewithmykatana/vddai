# W9D4 alert rules, dashboard, and runbook re-review

## 1. Reviewed subject

Review `W9D4-REV-2026-11-28-002`, 28 November 2026. Independent re-review
of `codex/w9d4-monitoring-runbook` in the W9D4 worktree. The approved
parent and `HEAD` are `814cdc4da39431526ff381e4ee54318ced7824c0`. The merge
base with `origin/master` is `1b9f6160883361bdb99298b256815197ccab8eba`.
The task-relative committed and staged ranges are empty. Seven monitoring
assets and three documentation files are the reviewed subject. Review
reports are separate audit evidence.

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
| `docs/engineering/monitoring-runbook.md` | `19dc0e60d7c512d311657a6204e91dff4327032aa66357c0981c6e509aaf74f5` |
| `docs/engineering/README.md` | `49069c1123a640aca06a4d59e247b314e04dc5ddfb7249383dea5e71742736db` |

## 2. Contract and selected findings

The approved [W9D4 task](https://app.notion.com/p/3ac0ab50ef6781eab479cfde7bfbd3a1)
requires a compact dashboard, actionable alerts including W9D3 quality
signals, and operator first response and rollback guidance. The plan includes
pinned Prometheus and Grafana, optional private monitoring, seven-day
aggregate retention, and password-protected Grafana on host loopback.

The human selected `VDDAI-REV-001` and `VDDAI-REV-002` from the
[original review](2026-11-27-w9d4-monitoring-runbook.md), preserved at
SHA-256 `670cd99a8fcdf63752df2084ef60ef8675ddd85a5f82cc8c2518b30fcbb24182`.
The runbook is the sole remediation file. Nine fingerprints match R1.
The [repository rules](../../AGENTS.md), [workflow](../engineering/agent-workflow.md),
and accepted [staging](../decisions/0014-single-host-staging-environment.md)
and [private metrics](../decisions/0015-private-observability.md) decisions
apply. W9D2 and W9D3 define the executable metrics and comparison semantics.
[Service metrics](../engineering/production-readiness.md#w9d2-service-and-queue-metrics)
[Quality reference](../engineering/production-readiness.md#w9d3-input-and-model-quality)

## 3. Verdict

**PASS.** Both prior findings are verified resolved. Independent QA is
eligible on the exact reviewed range.

## 4. Finding status

| ID | Severity | Status |
| --- | --- | --- |
| `VDDAI-REV-001` The setup path omits the matched quality reference | `MEDIUM` | `VERIFIED RESOLVED` |
| `VDDAI-REV-002` The quality incident capture points to a host-only listener | `MEDIUM` | `VERIFIED RESOLVED` |

### `VDDAI-REV-001`

The runbook now specifies building the W9D3 normal-validation reference
for the approved package, placing it at the ignored aggregate path in
the disposable checkout, and setting the matching `/app` path in the
worker environment. It documents optional omission and distinguishes
available, insufficient, mismatched, mixed, and missing-reference states.
[Reference setup and readiness](../engineering/monitoring-runbook.md#start-a-local-monitoring-session)

I independently built the merged Compose model with and without that exact
environment setting. The repository bind mapped the aggregate path into
`/app` and the worker had no host exporter mapping in either case. The
completed Coder closure receipt verifies the documented mounted reference
with 46 normal-validation samples. Comparison was unavailable with one
scored observation and available at 30 real package observations. After
the disposable worker restarted with the reference setting omitted, one
more real result produced `comparison: unavailable` and `warnings: null`.

### `VDDAI-REV-002`

Both quality incident procedures now link to the Compose-specific capture.
The runbook runs the worker's Python inside Compose against
`http://worker:9109/metrics` and feeds the UTF-8 snapshot to the existing
local report. I independently parsed the literal PowerShell block and ran
its file-writing and reporting pipeline with stubbed private scrape output.
It wrote BOM-free UTF-8 and distinguished unavailable comparison with null
warnings from available comparison with no warnings.
[Private capture](../engineering/monitoring-runbook.md#capture-and-check-the-worker-quality-report)

I matched the durable receipt to the inspected driver. The Coder exercised
the real `exec -T worker` transport and the local `scripts.report_quality_shift`
invocation using the documented endpoint. Both exporters remained private
and the public application `/metrics` route returned 404.

No new actionable findings surfaced.

## 5. Acceptance coverage

| Criterion | Evidence |
| --- | --- |
| Compact provisioned dashboard | Twelve panels and twenty checked PromQL expressions retain their R1 fingerprints. The disposable Docker proof confirmed protected Grafana, authenticated dashboard access, and the provisioned datasource. |
| Actionable local alerts | Pinned promtool found all ten alert rules and passed the provided tests on the current snapshot. Quality rules still require a usable comparison. |
| Private opt-in monitoring, protected password, and seven-day retention | The merged Compose model and Docker receipt show Grafana on host loopback and private Prometheus and exporters. The Docker proof reported seven days and an anonymous Grafana HTTP 401. |
| Operator first response, quality diagnostics, and rollback | The repaired runbook has working reference setup, private scrape and report paths, comparison interpretation, and the existing rollback approval boundaries. |

## 6. Checks run

- Reconciled Git branch, `HEAD`, merge base, empty index,
  `git diff --check`, ten SHA-256 file fingerprints, and R1 identity.
  `git check-ignore -v` confirmed the documented local reference path.
- Tested `docker compose -f docker-compose.yaml -f deploy/monitoring/compose.yaml
  config --quiet` and `config --format json` on a disposable Git archive with
  the exact files overlaid. Independent projections passed with and without
  the reference setting. The child environment discarded `GIT_*` and
  `COMPOSE_*` overrides.
- Pinned `promtool 3.16.0` passed `check config` and `test rules` on
  the same archive. The exact PowerShell capture passed independent syntax
  and stubbed-output reporter verification for both comparison outcomes.
- Checked the prior Coder Docker receipt `container-proof-shared-storage.log`
  at SHA-256 `b93d2bd9cabcaf810617710d8fb6206eb15daa7b71cc26f11199bb4c107c74d0`.
  The local Dockerfile app image
  `sha256:86fe698871dc878b850f694fa7e0c74c77a74975c0af7e30eeb5f6b255ed0ac3`
  was used for the real persisted prediction and private monitoring checks.
- Matched the final Coder closure receipt `container-proof-r2-retry.log`
  at `9590721e9589535bc5340ef25132929a673a76818093d26d274933cf17555582`
  and `probe-r2.py` at
  `2bc8b34a98090b5f4889768f77ff413a9be816785cab33cc5849470dfea9646c`.
  The receipt records the ordinary `/app` bind and reference path, matched
  and omitted-reference cases, successful private report capture, ten loaded
  rules, twelve panels, and label-scoped cleanup. The pinned monitoring
  images were verified through local offline aliases. An initial closure
  attempt ended during startup and cleaned up. The passing attempt used
  fixture-only resource isolation and a 180-second API cold-start grace.
- Exact Coder `scripts/verify.ps1 -PythonCommand $Pinned -IncludeFormatting
  -IncludeDockerConfig` returned **450 passed in 278.14 seconds** with
  disposable PostgreSQL 16.15 UTF-8, pinned requirements, one Alembic head,
  formatting policy, and base Compose validation.

## 7. Checks deferred

The real Docker runs and canonical gate are corroborating Coder evidence.
Independent QA may exercise the same local runtime and operator paths on
the exact subject. Staging and external alert delivery have separate scope.

## 8. Handoff

Independent QA may proceed on the fingerprinted subject. Verify the local
overlay and runtime evidence, matched-reference readiness, and the private
quality-report procedure. Documentation and Git actions follow their
established gates.

## 9. Residual context

Prometheus stores aggregate TSDB samples under the seven-day policy and
exposes rule evaluation state to the operator. The accepted runtime evidence
covers the disposable local environment and selected artifacts.

## Process-learning evidence

| Field | Record |
| --- | --- |
| Observation | The remediation verified both the literal command pipeline and the real private transport it depends on. |
| Evidence | The independent Compose projections and PowerShell check alongside the disposable closure receipt. |
| Impact | The documented setup and incident commands are tied to the selected runtime topology. |
| Recurrence | First observed for the W9D4 re-review. |
| Candidate improvement | Keep future operator-capture tests bound to the actual network path and local report command. |
| Authority note | This evidence confers no authority to change the workflow or its skills. |
