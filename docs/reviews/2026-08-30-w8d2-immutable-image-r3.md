# W8D2 Immutable Application Image Re-review R3

- Review ID: `W8D2-REV-2026-08-30-R3`
- Date: 2026-08-30
- Task: W8D2 — Build and publish an immutable application image, including the
  approved security amendment and the subsequent project-policy decision
- Prior reports: `docs/reviews/2026-08-30-w8d2-immutable-image.md` and
  `docs/reviews/2026-08-30-w8d2-immutable-image-r2.md`
- Base / HEAD / merge base: `4772a05971b033dde39dadcc7b5cf35676094f33`
- Branch: `codex/deploy/w8d2-immutable-image`
- Subject: the complete W8D2 working-tree delta, including modified and
  untracked task files; no implementation commit, push, pull request, registry
  publication, or hosted Actions result exists.

## Contract sources and acceptance criteria reviewed

- Approved W8D2 Planner handoff, human plan approval, W8D2 Security Amendment,
  explicit remediation approval for `VDDAI-REV-001`, and the subsequent human
  project-policy decision superseding `VDDAI-REV-002`.
- Root `AGENTS.md`; `docs/README.md`; `docs/catalog.yaml`; current production
  readiness and system-requirements contracts; ADRs 0012 and 0013; prior review
  reports; and the full working-tree range from the stated base.
- The immutable Compose entry point and tests, Dockerfile and context, CI
  workflow, dependency pins, operator documentation, and Coder verification
  evidence.

## Verdict

**PASS WITH DOCUMENTED RISK**

The direct mutable-reference bypass is closed. The repository-defined immutable
runtime entry point validates a canonical digest before it streams the Compose
document to Docker; the prior static deployment Compose file is absent. The
remaining hosted CI/GHCR verification is pending an authorized commit and push.

## Finding status summary

### VDDAI-REV-001 — HIGH — Immutable Compose mutable-reference bypass

- Status: `VERIFIED RESOLVED`
- Location: `scripts/run_immutable_compose.py:11-183` and
  `app/tests/test_run_immutable_compose.py:1-108`.
- Fresh evidence: with a provisioned artifacts path,
  `VDDAI_APPLICATION_IMAGE=ghcr.io/burymewithmykatana/vddai:latest` caused
  `python scripts/run_immutable_compose.py config --quiet` to exit `1` before
  Docker Compose ran. A canonical `name@sha256:<64-hex>` reference exited `0`.
  `docker-compose.immutable.yaml` no longer exists, so the R2 direct-file
  bypass is unavailable.
- Why closure is sufficient: `run_immutable_compose.py` now validates the
  complete shared image reference before generating and streaming the only
  repository-supported immutable Compose document through `docker compose -f -`.
  API and worker receive the same already-validated digest; the generated
  document retains their commands, read-only artifact mount, uploads volume,
  and absence of `.:/app` source substitution.
- Closure checks: focused immutable/container/security/OCI tests passed:
  `16 passed`; Coder also supplied successful digest runtime health and
  identical API/worker image-ID evidence.

### VDDAI-REV-002 — Superseded finding

- Status: `VERIFIED RESOLVED`
- The explicit human project-policy decision supersedes this finding. No active
  workflow, configuration, evidence, or acceptance-criterion requirement
  remains.

No actionable findings remain.

## Acceptance-criteria coverage

| Criterion | Evidence | Status |
|---|---|---|
| Minimal production image and final-image exclusions | Multi-stage Dockerfile, narrow runtime copies, Docker context exclusions, focused contract tests, and Coder image inspection. | Satisfied |
| API and worker execute one immutable revision | One validated digest is inserted into both generated service definitions; static mutable configuration was removed; Coder inspected identical image IDs and no source bind mount. | Satisfied |
| OCI source identity and digest promotion | OCI labels, SHA lookup-tag design, local validator, and digest-only deployment guidance are present. | Satisfied in local/source review |
| Quality gate and trusted publication restrictions | Static workflow inspection shows verification, strict audit, and image build feed the stable aggregate; isolated master-push publication uses least-privilege package write. | Satisfied in source review |
| Strict dependency audit and approved exception | Exact pins, strict audit command, exact approved advisory ID, and HS256 regression coverage are present. | Satisfied |
| Documentation and durable decisions | ADRs 0012/0013, catalog, system requirements, production readiness, and README describe the current boundary. | Satisfied |
| No W8D3 or ML/runtime-architecture expansion | No staging host, deployment, model promotion, queue, schema, or ML-contract change found. | Satisfied |

## Checks run

| Command / inspection | Outcome |
|---|---|
| `python scripts/run_immutable_compose.py config --quiet` with mutable `:latest` reference | Exited `1` before Compose invocation. |
| Same command with canonical digest reference | Exited `0`. |
| `Test-Path docker-compose.immutable.yaml` | `False`; the bypassable static file is absent. |
| `python -m pytest -q app/tests/test_run_immutable_compose.py app/tests/test_container_contract.py app/tests/test_security.py app/tests/test_validate_immutable_image.py` | Passed: `16 passed`; one pytest-asyncio deprecation warning. |
| `git diff --check` | Passed; no whitespace errors. |
| Direct implementation, documentation, prior-report, and full working-tree review | Completed; no new actionable finding. |

## Checks not run

- This Reviewer did not repeat the Coder's successful Docker build, OCI label,
  final-image-content, immutable API/worker runtime, strict PostgreSQL, full
  canonical, or dependency-audit checks. Those Coder results are recorded for
  QA's independent execution.
- Hosted GitHub Actions and GHCR publication cannot run until the reviewed
  subject is committed and pushed; neither action was authorized.

## Ordered handoff

1. QA: independently verify the reviewed current subject against W8D2,
   including the immutable entry-point rejection and digest runtime behavior,
   PostgreSQL, Docker, audit, documentation, and regression evidence.
2. After QA `PASS`, use the normal documentation and human merge workflow.
   Commit, push, hosted CI, registry publication, deployment, and model
   promotion remain separate human-authorized actions.

## Residual risks and assumptions

- The temporary `ecdsa==0.19.2` exception remains limited to
  `PYSEC-2026-1325` while the JWT contract remains HS256-only; it expires if
  the cryptographic architecture changes.
- The implementation is uncommitted, so hosted Actions, GHCR permissions,
  actual publication, and final task-SHA provenance remain pending an
  authorized commit and push.
- No generated image-IID file, test-database journal, static immutable Compose
  file, or ephemeral test container remains in the workspace.
