# W8D3 Reproducible Staging Environment Review

- Review ID: `W8D3-REV-2026-08-31`
- Date: 2026-08-31
- Task: W8D3 — Provision a reproducible staging environment
- Base / HEAD / merge base: `8113c89897c4bc446551f0ec7adf204bae3b8c38`
- Branch: `feat/w8d3-staging-provisioning`
- Subject: complete W8D3 working-tree delta, including modified and untracked
  files; no implementation commit, push, deployment, model action, or external
  infrastructure mutation exists.

## Contract sources and acceptance criteria reviewed

- Approved W8D3 Planner handoff and human approval; root `AGENTS.md`; nested
  `app/AGENTS.md`; docs index and catalog.
- ADRs 0007 through 0012, proposed ADR 0014, system requirements, production
  readiness, W8D2 immutable-runtime configuration, model resolver, health
  routes, and the complete subject files.
- Required outcomes: reproducible provisioning/configuration; one immutable
  API/worker image identity; external configuration/secrets; durable
  dependencies; HTTPS/stable endpoint planning; verifiable authenticated and
  health behavior; deployment and recovery documentation; and no deployment or
  model promotion.

## Verdict

**CHANGES REQUIRED**

The subject correctly introduces an additive digest-only staging entry point,
external host configuration, Caddy HTTPS ingress, and documentation. However,
two defects prevent it from proving that the required model artifact is ready
and from deterministically reusing durable state.

## Findings

### VDDAI-REV-001 — HIGH — Staging readiness does not require the selected model package

- Status: `OPEN`
- Location: `scripts/run_staging_compose.py:198-216,240-241`; generated API
  healthcheck requests only `/health`, while `app/api/routes/health.py:28-42`
  exposes the fail-closed package-selection check separately at `/health/model`.
- Evidence: the API healthcheck succeeds whenever the process answers
  `/health`; its result gates both worker and Caddy. An absent/invalid registry,
  package, feature bank, or checkpoint makes `/health/model` return `503` but
  does not prevent worker/Caddy startup. The runbook tells the operator to
  inspect `/health/model` only after `up -d`.
- Failure scenario: an artifacts directory is absent, incomplete, or contains
  no promoted selection. The deployment appears healthy at the Compose/Caddy
  boundary, then the worker terminally fails every claimed job under the
  existing fail-closed worker policy.
- Why it matters: W8D3 requires staging to run the approved immutable
  application/model artifacts and to make health verification reliable; this
  admits a stack without a usable model package.
- Required action: make the generated staging API readiness check require both
  ordinary API liveness and successful `/health/model` selection before worker
  and Caddy dependencies are released. Preserve safe health response fields and
  no-public-secret behavior. Add generated-document and failure-path coverage
  showing model-unavailable readiness is non-healthy.
- Closure verification: focused staging tests must assert the model-health
  probe; a real digest-shaped `config --quiet` render must pass; and a
  deliberately unavailable model selection must keep the dependent services
  from becoming ready in an applicable disposable Compose test.

### VDDAI-REV-002 — MEDIUM — Compose durable-volume identity depends on ambient project naming

- Status: `OPEN`
- Location: `scripts/run_staging_compose.py:260-274`; the generated document
  declares named volumes but no top-level Compose project `name`.
- Evidence: Compose derives a project name from its invocation context unless
  an explicit top-level name or environment override is supplied. The runner
  streams the document through `docker compose -f -`, so an operator moving the
  repository checkout, invoking through a different directory, or supplying
  `COMPOSE_PROJECT_NAME` can receive different `postgres_data`,
  `vddai_uploads`, and Caddy volumes.
- Failure scenario: a nominal redeploy starts against new empty PostgreSQL and
  uploads volumes rather than the intended staging state. Recovery and rollback
  documentation then refers to volumes that may not be the ones serving the
  endpoint.
- Why it matters: durable dependency handling and reproducible provisioning
  require stable volume identity across normal operator invocation contexts.
- Required action: set and document one fixed staging Compose project name in
  the generated document, and add regression coverage for the top-level name
  and expected volume namespace. Do not change local-development Compose.
- Closure verification: focused tests and `python scripts/run_staging_compose.py
  config --quiet` must pass, with rendered volume names stable despite the
  caller directory or ambient Compose-project setting.

## Acceptance-criteria coverage

| Criterion | Review evidence | Status |
|---|---|---|
| Reproducible provisioning/configuration | Digest validation, external env-file validation, template, and generated Compose are present. Ambient volume naming defeats full reproducibility. | Not satisfied (`VDDAI-REV-002`) |
| Immutable API and worker identity | One validated `VDDAI_APPLICATION_IMAGE` is used for both, without source mount. | Satisfied |
| Secrets outside source control | External env-file requirement, template validation, and ignore rule are present. | Satisfied |
| Durable dependencies | Internal Postgres/Redis, named volumes, and recovery prose are present; volume identity is ambient. | Not satisfied (`VDDAI-REV-002`) |
| HTTPS and stable endpoint | Caddy/FQDN configuration and ports 80/443 are present. | Satisfied in source review |
| Health/authenticated behavior verifiable | Existing safe endpoints remain, but model readiness does not gate dependent services. | Not satisfied (`VDDAI-REV-001`) |
| Deployment and rollback/recovery implications | ADR 0014 and production-readiness documentation address worker stop, backups, and downgrade preconditions. | Partially satisfied (`VDDAI-REV-002`) |
| No production deployment or model promotion | No external action, registry mutation, or promotion code found. | Satisfied |

## Checks run

| Command / inspection | Outcome |
|---|---|
| `git diff --check` | Passed. |
| `python -m pytest -q --basetemp=.pytest_tmp/w8d3-final app/tests/test_run_staging_compose.py app/tests/test_run_immutable_compose.py app/tests/test_container_contract.py` | Coder evidence: passed, `19 passed`. |
| `python -m pip check` | Coder evidence: passed. |
| `python scripts/validate_python_formatting.py` | Coder evidence: passed for the two changed Python files. |
| `python scripts/validate_docs.py` | Coder evidence: passed, 25 canonical documents and 65 Markdown files. |
| `python3 scripts/run_staging_compose.py config --quiet` with disposable template-only values and digest-shaped references | Coder evidence: passed. |
| `docker compose -f docker-compose.yaml config --quiet` | Coder evidence: passed. |
| Direct implementation, documentation, contracts, health, resolver, and full working-tree inspection | Completed; findings above. |

## Checks not run

- The independent Reviewer did not run Docker services, obtain TLS, create a
  host, authenticate to GHCR, or execute a live authenticated smoke test;
  those are outside review authority and W8D4/external human-gated work.
- The canonical verification gate was launched by the Coder but its terminal
  status was not observable from the mixed WSL/Windows runner after pytest
  began. It is not accepted as passing evidence.

## Ordered remediation handoff

1. Human: explicitly approve remediation for `VDDAI-REV-001` and
   `VDDAI-REV-002`. This report does not authorize implementation.
2. Coder: modify only the staging generator, its focused tests, and the
   resulting staging/ADR documentation required to close these two findings.
   Preserve W8D2, local development Compose, public API contracts, registry
   promotion policy, and all W8D4 scope exclusions.
3. Coder: provide focused test, Compose-render, documentation-validation, and
   applicable canonical-gate evidence. Do not deploy, create infrastructure,
   issue secrets, or promote/roll back a model.
4. Reviewer: create a numbered re-review, retain both finding IDs, and verify
   closure before QA begins.

## Residual risks and assumptions

- The single-host local storage and local registry boundary remains deliberate;
  it is not HA and requires operator-owned backups.
- Private GHCR pull credentials, DNS, certificate issuance, host capacity, and
  live staging deployment remain explicit human-controlled external actions.
- W8D4 owns live authenticated smoke testing and rollback execution.

## Process-learning evidence

- Observation: Reviewing generated Compose state separately from its static
  source exposed readiness and volume-identity gaps not covered by basic digest
  assertions.
- Evidence: `scripts/run_staging_compose.py`; `app/tests/test_run_staging_compose.py`;
  ADRs 0009, 0010, and 0014.
- Impact: Prevents a nominally healthy staging endpoint from serving no valid
  model and prevents accidental durable-state replacement.
- Recurrence: first observed.
- Candidate improvement: None; this is a task-specific regression-test gap.
- Authority note: This evidence does not authorize a skill or workflow change.
