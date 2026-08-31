# ADR 0014 — Reproducible Single-Host Staging Environment

- Status: Accepted
- Date: 2026-08-31

## Context

ADR 0012 establishes an immutable application-image boundary but intentionally
does not select a staging host, ingress, TLS, durable-dependency configuration,
or secret-management procedure. The v0.1 pilot still uses local filesystem
image storage, a local SQLite model registry, and a database-backed worker.

W8D3 needs a reproducible staging environment without creating a production
environment, introducing a distributed storage system, or changing model
promotion policy.

## Decision

VDDAI staging is one Linux host running Docker Compose. The host runs the API,
worker, PostgreSQL, Redis, and Caddy reverse proxy on one Compose network.
Caddy is the only public-facing service, binds ports 80 and 443, redirects to
HTTPS, and obtains certificates for one explicitly configured staging FQDN.
PostgreSQL and Redis have no host-published ports.

`scripts/run_staging_compose.py` is the repository-owned staging entry point.
The human-approved entry-point amendment extends
[ADR 0012](0012-immutable-application-image-publication.md)'s original
sole-entry-point restriction: staging has an additive launcher that reuses
W8D2 application-image and artifact-path validation, constructs its own Compose
document, and invokes Compose independently. It does not replace or change
`scripts/run_immutable_compose.py` or the source-mounted local-development path.
This amendment authorizes no infrastructure provisioning or live deployment.

It requires canonical digest references for the W8D2 application image and the
PostgreSQL, Redis, and Caddy dependency images. API and worker receive the
same application digest and no source bind mount. It also requires a
host-managed staging environment file outside the repository, a public FQDN,
and a provisioned runtime-artifact directory. It rejects template JWT and
PostgreSQL credentials, unsafe environment identity, mutable images, and a
different storage or registry path before Docker Compose runs.

The runner fixes the Compose project name to `vddai-staging`, including when a
caller's environment supplies `COMPOSE_PROJECT_NAME`. PostgreSQL, uploads, and
Caddy named volumes therefore retain a stable deployment namespace across
normal invocation directories and operator shells.

The host-managed environment file supplies application settings and PostgreSQL
bootstrap credentials. It is permission-restricted, ignored by Git, and must
not be printed in command output. Private GHCR pulls use a pull-only operator
credential held in the host Docker credential store, not a repository file.

Named Docker volumes retain PostgreSQL state, prediction uploads, and Caddy
certificate/configuration state. The provisioned artifact directory is mounted
read-only at `/app/artifacts`; it must contain the already approved registry,
package, feature bank, and ResNet checkpoint. Serving continues to resolve the
registry's explicit `production` selection. Staging provisioning never
registers, promotes, rolls back, regenerates, or downloads a model artifact.

## Operations and Recovery

Before an image change that can migrate schema, stop the worker, retain a
backup of PostgreSQL and the artifact snapshot, then start the selected digest.
Do not run old and new worker versions together. Schema downgrade follows the
preconditions in ADRs 0010 and 0011: stop workers and confirm no processing
work depends on retry, lease, or admission metadata before executing a
downgrade. Restoring PostgreSQL, uploads, and the exact artifact snapshot is a
single-host recovery operation; loss of the host without backups is not
automatically recoverable.

W8D4 owns a live authenticated smoke test and rollback exercise. W8D3 exposes
the stable HTTPS endpoint plus `/health`, `/health/db`, and `/health/model` for
that later work. No production deployment, paid resource creation, DNS change,
or model promotion is authorized by this ADR.

## Consequences

- Staging is inexpensive and operationally small, but is not highly available.
- The local filesystem storage and local registry remain valid only because API
  and worker share one host and volumes.
- Every selected container image and application/model identity is explicit,
  avoiding tag or ambient-state deployment drift.
- The operator owns DNS, GHCR pull access, secret injection, backups, and
  recovery until a separately approved platform architecture changes them.
