# W8D2 Immutable Application Image Re-review

- Review ID: `W8D2-REV-2026-08-30-R2`
- Date: 2026-08-30
- Task: W8D2 — Build and publish an immutable application image, including the
  approved security amendment and the subsequent project-policy decision
- Prior review: `docs/reviews/2026-08-30-w8d2-immutable-image.md`
- Base / HEAD / merge base: `4772a05971b033dde39dadcc7b5cf35676094f33`
- Branch: `codex/deploy/w8d2-immutable-image`
- Subject: the complete W8D2 working-tree delta, including modified and
  untracked task files; there is no implementation commit, push, pull request,
  registry publication, or hosted Actions result.

## Contract sources and acceptance criteria reviewed

- Approved W8D2 Planner handoff, human plan approval, W8D2 Security Amendment,
  explicit remediation approval for `VDDAI-REV-001`, and the subsequent human
  project-policy decision superseding `VDDAI-REV-002`.
- Root `AGENTS.md`; `docs/README.md`; `docs/catalog.yaml`; current production
  readiness and system-requirements contracts; ADRs 0012 and 0013; the prior
  review report; and the complete working-tree range from the stated base.
- Immutable runtime Compose configuration and invocation boundary, Dockerfile,
  Docker context exclusions, CI workflow, dependency pins, focused tests, and
  operator documentation.

## Verdict

**CHANGES REQUIRED**

`VDDAI-REV-001` remains open. The new wrapper rejects mutable references only
when the operator uses it, but the deployment-oriented Compose configuration
can still be invoked directly with `:latest`. That directly bypasses the
required immutable-image boundary.

## Findings

### VDDAI-REV-001 — HIGH — Direct immutable Compose invocation still accepts mutable images

- Status: `STILL OPEN`
- Location: `docker-compose.immutable.yaml:3,34`; the new validator at
  `scripts/run_immutable_compose.py:11-83` is an optional wrapper rather than
  an enforced Compose boundary.
- Fresh evidence: with `VDDAI_ARTIFACTS_PATH` set to the local provisioned
  artifacts directory and
  `VDDAI_APPLICATION_IMAGE=ghcr.io/burymewithmykatana/vddai:latest`, direct
  execution of `docker compose -f docker-compose.immutable.yaml config --quiet`
  exited `0`. Under the same environment,
  `python scripts/run_immutable_compose.py config --quiet` correctly exited
  `1`; a canonical digest reference correctly exited `0` through the wrapper.
- Failure scenario: an operator or later deployment automation can use the
  declared deployment-oriented Compose file directly. API and worker then
  accept the mutable tag from the environment, allowing a registry update to
  change the reviewed artifact without an explicit digest selection.
- Why it matters: documentation and an optional helper cannot make the Compose
  configuration itself immutable. This contradicts ADR 0012 and the W8D2
  requirement that mutable references such as `latest` are rejected.
- Required action: make the deployment-oriented Compose contract itself reject
  non-digest application-image references, or remove the bypass so every
  supported invocation necessarily performs the existing validation before
  Compose parses service images. Preserve one shared digest reference for API
  and worker, existing runtime mounts and commands, and local development
  Compose behavior. Add an integration-level regression test for the direct
  supported invocation boundary, not only the wrapper function.
- Closure verification: using a mutable tag against every supported immutable
  Compose invocation must fail before service startup; a digest reference must
  configure and start the API and worker from the same inspected image ID with
  no `.:/app` mount.

### VDDAI-REV-002 — Superseded finding

- Status: `VERIFIED RESOLVED`
- The explicit human project-policy decision supersedes this finding. It
  requires no implementation action and introduces no active workflow,
  configuration, evidence, or acceptance-criterion requirement.

No other actionable findings were identified in this re-review.

## Acceptance-criteria coverage

| Criterion | Re-review evidence | Status |
|---|---|---|
| Minimal production image and final-image exclusions | Multi-stage Dockerfile, narrow runtime copies, Docker context exclusions, and focused container contract test remain present. | Satisfied in source review |
| API and worker execute one immutable revision | Both services share one image variable and have no source bind mount, but the variable accepts mutable tags when Compose is invoked directly. | Not satisfied (`VDDAI-REV-001`) |
| OCI source identity and digest promotion | Docker labels, local validator, SHA lookup-tag design, and digest documentation remain present. | Satisfied in source review; hosted evidence pending |
| Quality gate and trusted publication restrictions | Static workflow review shows the aggregate depends on verification, audit, and image jobs; the isolated publish job is master-push-only and has `packages: write`. | Satisfied in source review; hosted evidence pending |
| Strict audit and approved exception | Exact pins and strict audit command with one approved advisory ID remain present. | Satisfied in source review |
| Documentation and durable decisions | ADRs 0012/0013, catalog, production readiness, system requirements, and README are consistent with the intended image boundary. | Partially satisfied because the direct Compose behavior contradicts the documented invariant |
| No W8D3 or ML/runtime-architecture expansion | No staging host, deployment, model promotion, queue, schema, or ML-contract change was found. | Satisfied |

## Checks run

| Command / inspection | Outcome |
|---|---|
| Direct `docker compose -f docker-compose.immutable.yaml config --quiet` with a `:latest` image | **Exited 0 unexpectedly**; confirms `VDDAI-REV-001` remains open. |
| `python scripts/run_immutable_compose.py config --quiet` with the same mutable image | Exited 1 before Compose invocation. |
| Same wrapper command with a canonical digest reference | Exited 0. |
| `python -m pytest -q app/tests/test_run_immutable_compose.py app/tests/test_security.py app/tests/test_container_contract.py app/tests/test_validate_immutable_image.py` | Passed: `15 passed`; one pytest-asyncio deprecation warning. |
| `.venv\Scripts\python.exe -m pip install --dry-run --requirement requirements.txt` | Passed; all exact pins resolved from the installed environment. |
| `git diff --check` | Passed; no whitespace errors. |
| Direct source and complete working-tree review | Completed. |

## Checks not run

- The full canonical suite, strict PostgreSQL gate, Docker image build and
  inspection, and immutable-stack health path were not repeated by this
  Reviewer. The Coder supplied successful local evidence; these remain
  independent QA scenarios after the finding closes.
- Hosted GitHub Actions and GHCR publication were not run because the subject
  remains uncommitted and no push, PR mutation, or registry publication was
  authorized.

## Ordered remediation handoff

1. Human: explicitly approve a narrowly scoped remediation for
   `VDDAI-REV-001`; this re-review does not authorize implementation.
2. Coder: eliminate the direct mutable-reference bypass and add the required
   direct-boundary regression coverage. Do not change local-development
   Compose, image publication rules, dependencies, authentication, ML
   contracts, or infrastructure scope.
3. Coder: rerun the finding closure checks and applicable repository evidence,
   then return a standalone remediation report without committing, pushing,
   publishing, deploying, or promoting.
4. Reviewer: create an `R3` report, retain both finding IDs, and independently
   verify closure before QA begins.

## Residual risks and assumptions

- The approved temporary `ecdsa==0.19.2` exception remains restricted to
  `PYSEC-2026-1325` while the JWT contract remains HS256-only. It expires if
  the cryptographic architecture changes.
- Task-SHA provenance, hosted CI execution, GHCR permission behavior, and
  registry publication cannot be proven until an authorized commit and push.
- No generated image-IID or test-database journal remains in the working tree.
