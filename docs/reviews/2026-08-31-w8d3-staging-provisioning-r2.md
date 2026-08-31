# W8D3 Reproducible Staging Environment Re-review R2

- Review ID: `W8D3-REV-2026-08-31-R2`
- Date: 2026-08-31
- Task: W8D3 — Provision a reproducible staging environment
- Prior report: `docs/reviews/2026-08-31-w8d3-staging-provisioning.md`
- Base / HEAD / merge base: `8113c89897c4bc446551f0ec7adf204bae3b8c38`
- Branch: `feat/w8d3-staging-provisioning`
- Subject: complete current W8D3 working-tree delta, including modified and
  untracked files; no implementation commit, push, deployment, model action,
  or external infrastructure mutation exists.

## Contract sources and acceptance criteria reviewed

- Approved W8D3 Planner handoff and human approval; approved remediation of
  `VDDAI-REV-001` and `VDDAI-REV-002`; root `AGENTS.md`; nested `app/AGENTS.md`.
- ADRs 0007 through 0012, proposed ADR 0014, system requirements, production
  readiness, W8D2 immutable-runtime configuration, model health route, and the
  complete current working-tree subject.

## Verdict

**PASS WITH DOCUMENTED RISK**

Both selected findings are resolved. The remaining verification-evidence
limitation is carried forward: the prior Coder invocation of the canonical
gate could not retain a terminal result after pytest began in the mixed
WSL/Windows runner. It is not a correctness finding or evidence that the gate
passed; QA must determine whether it can obtain current canonical-gate evidence
in an appropriate environment.

## Finding status summary

### VDDAI-REV-001 — HIGH — Staging readiness does not require the selected model package

- Status: `VERIFIED RESOLVED`
- Fresh location: `scripts/run_staging_compose.py:208-222,244-245` and
  `app/tests/test_run_staging_compose.py:45-94`.
- Fresh evidence: the generated API healthcheck requests `/health` and then
  `/health/model`; an unavailable model selection returns its established
  non-2xx `503`, causing the Docker healthcheck to fail before the worker or
  Caddy `depends_on: service_healthy` conditions are released. The focused test
  asserts the model-health URL in the generated document.
- Closure verification: `python -m pytest -q --basetemp=.pytest_tmp/w8d3-rereview
  app/tests/test_run_staging_compose.py app/tests/test_run_immutable_compose.py
  app/tests/test_container_contract.py` passed: `19 passed`.

### VDDAI-REV-002 — MEDIUM — Compose durable-volume identity depends on ambient project naming

- Status: `VERIFIED RESOLVED`
- Fresh location: `scripts/run_staging_compose.py:33,196-197,326-334`; test
  coverage at `app/tests/test_run_staging_compose.py:54-94`; operations guidance
  at `docs/engineering/production-readiness.md`.
- Fresh evidence: the generated document has top-level `name:
  vddai-staging`, and the Docker invocation includes `--project-name
  vddai-staging`, which has precedence over ambient Compose project naming.
  PostgreSQL, uploads, and Caddy volumes therefore retain the deterministic
  `vddai-staging_*` namespace across normal caller directories and shells.
- Closure verification: the focused test asserts both the generated name and
  command-line project argument; Coder additionally rendered configuration with
  `COMPOSE_PROJECT_NAME=unsafe-name` successfully.

No new actionable findings were identified.

## Acceptance-criteria coverage

| Criterion | Re-review evidence | Status |
|---|---|---|
| Reproducible provisioning/configuration | Fixed project identity, digest validation, external env-file validation, and template are present. | Satisfied in source review |
| Immutable API and worker identity | One digest variable remains shared with no source mount. | Satisfied |
| Secrets outside source control | Host-managed env-file and template validation remain intact. | Satisfied |
| Durable dependencies | Internal Postgres/Redis plus deterministic named-volume namespace are present. | Satisfied |
| HTTPS and stable endpoint | Caddy/FQDN configuration and ports 80/443 remain present. | Satisfied in source review |
| Health/authenticated behavior verifiable | Model selection now gates service readiness; existing safe endpoints remain unchanged. | Satisfied |
| Deployment and rollback/recovery implications | ADR 0014 and production-readiness guidance remain current. | Satisfied |
| No production deployment or model promotion | No external action, registry mutation, or promotion code found. | Satisfied |

## Checks run

| Command / inspection | Outcome |
|---|---|
| `git diff --check` | Passed. |
| `python -m pytest -q --basetemp=.pytest_tmp/w8d3-rereview app/tests/test_run_staging_compose.py app/tests/test_run_immutable_compose.py app/tests/test_container_contract.py` | Passed: `19 passed`. |
| `python scripts/validate_docs.py` | Passed: 25 canonical documents and 66 Markdown files. |
| Direct full-subject, remediation, healthcheck, Compose command, documentation, and secret-boundary inspection | Completed; no new actionable finding. |

## Checks not run

- No live Docker service, GHCR pull, TLS issuance, host provisioning, DNS
  mutation, authenticated smoke test, or rollback was run; each remains outside
  review authority and/or belongs to W8D4 and external human approval.
- The canonical repository gate's terminal result remains unavailable from the
  mixed local runner; do not treat it as passing evidence.

## Ordered handoff

1. QA: independently verify the current reviewed subject. Before a final PASS,
   obtain or explicitly classify the canonical-gate evidence limitation and
   exercise the staged configuration boundaries applicable without external
   deployment.
2. After QA `PASS`, Documentation may perform its documentation-only lifecycle
   pass. No commit, push, staging deployment, DNS action, secret issuance,
   production deployment, or model promotion is authorized by this report.

## Residual risks and assumptions

- Single-host local storage and registry remain deliberate pilot limitations;
  backups and operator recovery remain required.
- Private GHCR credentials, DNS, TLS issuance, host capacity, and any live
  deployment remain explicit human-controlled external actions.
- W8D4 owns a live authenticated smoke test and rollback exercise.

## Process-learning evidence

- Observation: For generated deployment configuration, asserting both rendered
  document fields and the Docker invocation is necessary to close ambient-tool
  precedence risks.
- Evidence: `VDDAI-REV-002`; `scripts/run_staging_compose.py`; focused test
  command above.
- Impact: Confirms that the volume namespace cannot drift through a caller's
  `COMPOSE_PROJECT_NAME` environment setting.
- Recurrence: first observed.
- Candidate improvement: None; the remediation added the needed task-level
  coverage.
- Authority note: This evidence does not authorize a skill or workflow change.
