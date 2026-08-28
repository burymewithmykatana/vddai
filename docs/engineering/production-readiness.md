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

## Hosted W8D1 quality gate

`.github/workflows/ci.yml` is the authoritative hosted merge-quality gate for
pull requests, `master` pushes, and manual dispatches. It provisions an
ephemeral PostgreSQL 16 service and runs the complete canonical suite without
the default PostgreSQL skips, then runs `scripts/run_production_gate.py` as the
strict W7D4 regression verdict. The same mandatory job validates exact Python,
pip, and requirement pins, documentation, one Alembic head, Black formatting
for Python files added or changed in the Git comparison, and Docker Compose
configuration. A separate mandatory job builds the application image without
publishing it.

The stable aggregate check is `VDDAI v0.1.0 quality gate`. It succeeds only when
both required jobs report `success`; failure, skip, cancellation, timeout, or
unavailable evidence remains non-green. The workflow has read-only repository
permission and uses no production secret, GitHub environment, registry
credential, or production infrastructure.

Hosted CI does not provision ignored registry, package, feature-bank, or model
weight files and does not run the data-creating deployed probe. The deployed
real-inference proof remains environment-specific release evidence. CI success
does not make the full W7D4 release outcome green by itself and never authorizes
merge, release, deployment, or model promotion.

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

Do not use `docker compose down -v` as part of this gate.

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
