# ADR 0012 — Immutable Application Image Publication

- Status: Accepted
- Date: 2026-08-29

## Context

The API and prediction worker currently build independently from one
development-oriented Dockerfile and Compose replaces their application files
with a source bind mount. That is useful for local development but cannot prove
that API and worker execute the same reviewed artifact in a staging or release
environment. The repository also needs a reproducible, source-traceable image
publication boundary without deploying the application or changing the model
registry and promotion contracts.

## Decision

The application image is built from the pinned `python:3.14.3` base-image
digest with a builder stage that creates the pinned Python environment and a
minimal runtime stage. The runtime stage contains only that environment and
the application runtime sources required by both processes: `app/`, `ml/`,
`alembic/`, and `alembic.ini`. Tests, documentation, scripts, Git metadata,
local uploads, generated model artifacts, registries, feature banks, datasets,
and cached weights do not enter the final image.

The image records `org.opencontainers.image.source`,
`org.opencontainers.image.revision`, and `org.opencontainers.image.version`.
CI publishes the Linux/amd64 artifact only to the private GitHub Container
Registry package:

```text
ghcr.io/burymewithmykatana/vddai:sha-<full-commit-sha>
```

The SHA tag is a lookup convenience. The registry digest returned by the
successful publish (`ghcr.io/burymewithmykatana/vddai@sha256:...`) is the only
authoritative promotion and deployment identity. `latest` is never published
or used for deployment. A later staging or release action must receive the
exact digest explicitly; it must not discover an ambient registry tag.

The existing `docker-compose.yaml` remains the source-mounted local-development
path. `scripts/run_immutable_compose.py` is the W8D2 deployment-oriented
Compose entry point: it validates one digest-pinned
`VDDAI_APPLICATION_IMAGE` value before supplying the configuration to Compose.
The API and worker retain their distinct commands and have no application source
bind mount or build instruction. The path keeps the local filesystem storage
boundary by sharing a named uploads volume and mounting intentionally
provisioned runtime artifacts read-only at `/app/artifacts`. PostgreSQL and
Redis remain the existing dependencies; the prediction queue remains
database-backed.

The human-approved W8D3 amendment in
[ADR 0014](0014-single-host-staging-environment.md) extends the original
sole-entry-point restriction with a separate `scripts/run_staging_compose.py`
launcher. It reuses W8D2 application-image and artifact-path validation while
owning the staging Compose document and invocation. The existing W8D2 entry
point, immutable-image contract, publication workflow, and local-development
behavior remain unchanged.

The CI workflow keeps its stable aggregate quality gate. It adds a read-only
dependency audit of the installed pinned Python environment with
`pip-audit==2.10.1`. It builds and locally inspects every candidate image
without publishing it. Only a push to `master` after the aggregate gate reports
success can publish. The isolated publication job has only `contents: read` and
`packages: write`; it authenticates to GHCR with the GitHub Actions short-lived
`GITHUB_TOKEN`. Pull requests, manual dispatches, and any failed, skipped,
cancelled, or incomplete quality result never publish.

ADR 0013 records the only temporary audit exception. The audit stays strict and
ignores only the approved exact advisory ID; every other finding blocks the
quality gate.

## Consequences

- API and worker can run from one immutable image digest while retaining their
  established entry points and runtime dependencies.
- Image provenance is traceable to the source repository and full commit SHA.
- Ignored ML artifacts remain explicitly provisioned runtime dependencies;
  image publication does not package, select, promote, or download them.
- The private GHCR package creates a later pull-authentication requirement for
  staging/release provisioning. W8D2 does not provision an environment, grant
  host credentials, deploy, or promote a model.
- `pip-audit` reports known Python dependency vulnerabilities in the installed
  environment. It is not an operating-system image scan, SBOM, provenance
  attestation, image signing mechanism, or proof of application/runtime
  security.
- A new image is rebuilt for publication after successful verification. The
  pinned base, pinned dependencies, build inputs, source labels, SHA tag, and
  recorded digest provide reproducible evidence; the digest remains the exact
  artifact identity.

## Verification

The permanent container contract tests assert the multi-stage runtime boundary,
Docker context exclusions, and the immutable Compose shared-image/no-source-mount
contract. `scripts/validate_immutable_image.py` verifies a locally built image
ID and its OCI source labels. The hosted workflow verifies the source SHA labels
before publication, runs the dependency audit, and records the registry digest
and full immutable reference in the publication-job summary.
