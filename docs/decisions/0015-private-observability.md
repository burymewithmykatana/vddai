# ADR 0015 — Private service metrics

- Status: Accepted
- Date: 2026-11-27

## Context

W9D2 needs operational evidence about API traffic, queue state, and worker
outcomes. The staging ingress and TLS boundary already established by
[ADR 0014](0014-single-host-staging-environment.md) applies to the pilot.

## Decision

Expose aggregate Prometheus metrics through optional HTTP listeners owned
separately by the API and worker processes. Disable both by default. An
enabled listener binds to loopback or, for an approved private deployment,
the process hostname’s RFC 1918 IPv4 address. Keep metrics ports off public
interfaces and public ingress. Operators confine access to the local host
or the approved internal network.

Use bounded labels and observe the existing request and worker transaction
boundaries. Collect queue state through a bounded, read-only PostgreSQL
snapshot. The exporter is optional and emits a safe diagnostic if startup
fails. Metric observation does not grant access to stored predictions,
image contents, or model artifacts.

## Consequences

Counters reset with the service process. Scrape availability, database
snapshot availability, worker poll readiness, and observed model readiness
are distinct operational signals. Dashboards, alerting, and measured workload
targets are delivered through the subsequent approved Week 9 tasks.

See the
[metrics operator guide](../engineering/production-readiness.md#w9d2-service-and-queue-metrics)
for configuration, metric semantics, and evidence.
