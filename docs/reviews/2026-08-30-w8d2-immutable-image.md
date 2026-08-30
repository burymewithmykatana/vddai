# W8D2 Immutable Application Image Review

- Review ID: `W8D2-REV-2026-08-30`
- Date: 2026-08-30
- Task: W8D2 — Build and publish an immutable application image, including the
  approved security amendment
- Base / HEAD / merge base: `4772a05971b033dde39dadcc7b5cf35676094f33`
- Branch: `codex/deploy/w8d2-immutable-image`
- Subject: the complete unstaged W8D2 implementation. There is no W8D2
  implementation commit, push, pull request, registry publication, or hosted
  Actions result.

## Verdict

**CHANGES REQUIRED**

The production image, CI, audit, and shared-image design are largely within
scope. The deployment-oriented Compose path accepts floating image tags,
including `latest`, which violates the immutable deployment contract. QA is
ineligible until this finding is closed and independently re-reviewed.

## Finding

### VDDAI-REV-001 — HIGH — Immutable Compose path accepts mutable image references

- Status: `OPEN`
- Location: `docker-compose.immutable.yaml:3,34`; coverage gap in
  `app/tests/test_container_contract.py:38-41`.
- Evidence: with `VDDAI_ARTIFACTS_PATH` set to the provisioned artifacts
  directory, the reviewer set
  `VDDAI_APPLICATION_IMAGE=ghcr.io/burymewithmykatana/vddai:latest` and ran
  `docker compose -f docker-compose.immutable.yaml config --quiet`. It exited
  successfully.
- Failure scenario: an operator can follow the deployment-oriented path with a
  moving tag. A later registry update can change the reviewed API and worker
  artifact without an explicit digest selection.
- Required action: add a repository-owned validation/invocation boundary that
  rejects every non-digest `VDDAI_APPLICATION_IMAGE` value before immutable
  Compose is used. It must require a canonical
  `name@sha256:<64-hex-digest>` reference, retain the shared API/worker value,
  be the documented deployment-oriented command, and have focused regression
  coverage.
- Closure verification: the mutable-tag configuration must fail before Compose
  startup; a digest-pinned reference must pass configuration and start both
  services from the same inspected image ID without a source bind mount.

## Acceptance-criteria coverage

| Criterion | Review evidence | Status |
|---|---|---|
| Minimal production image and exclusion of runtime ML state | Multi-stage `Dockerfile`, narrow runtime copies, `.dockerignore`, image-content contract test, and Coder-built image inspection. | Satisfied in source review |
| API and worker share one revision without source replacement | Both immutable services use one variable and preserve their established commands. | Partially satisfied; mutable-reference enforcement is open (`VDDAI-REV-001`) |
| OCI source identity and promotion by digest | OCI labels, SHA lookup tag, digest summary, and validator are present. The uncommitted local image label is only wiring evidence; authoritative task-SHA evidence awaits an authorized commit/push. | Design satisfied; hosted evidence pending |
| CI publication restrictions and least privilege | `publish` is master-push-only, depends on successful aggregate gate, uses isolated `packages: write`, and uses `GITHUB_TOKEN`; PR and manual events cannot publish. | Satisfied in static review; hosted execution pending |
| Strict dependency audit and approved remediation | Requirements pin `cryptography==50.0.0` and `pyasn1==0.6.4`; bootstrap/CI pin `pip==26.2`; CI retains strict audit with only `PYSEC-2026-1325`. | Technically satisfied |
| HS256 invariant and no crypto-architecture change | `app/core/security.py` remains HS256-only; new regression test checks token header and decode path. | Satisfied |
| Documentation and ADRs | ADRs 0012/0013, catalog, system requirements, production readiness, and README explain the boundary and exception. | Satisfied in source review |
| No W8D3/deployment/model-promotion expansion | No host deployment, model promotion, schema, queue, storage-architecture, or application behavior change was found. | Satisfied |

## Checks run

| Command / inspection | Outcome |
|---|---|
| `docker compose -f docker-compose.immutable.yaml config --quiet` with `VDDAI_APPLICATION_IMAGE=ghcr.io/burymewithmykatana/vddai:latest` | Passed unexpectedly; produced `VDDAI-REV-001`. |
| `python -m pytest -q app/tests/test_security.py app/tests/test_container_contract.py app/tests/test_validate_immutable_image.py` | Passed: `8 passed`, one pytest-asyncio deprecation warning. |
| `.venv\Scripts\python.exe -m pip_audit --local --strict --ignore-vuln PYSEC-2026-1325` | Passed: `No known vulnerabilities found, 1 ignored`. |
| `.venv\Scripts\python.exe -m pip check` | Passed: `No broken requirements found.` |
| `python scripts/validate_docs.py` | Passed: 24 canonical documents, 57 Markdown files. |
| `git diff --check` | Passed; no whitespace errors. |

## Checks not run

- The complete canonical suite, disposable PostgreSQL gate, Docker build,
  final-image inspection, and immutable-stack health path were not repeated by
  this Reviewer. The Coder supplied successful local evidence, but these remain
  QA-owned independent scenarios.
- Hosted GitHub Actions and GHCR publication were not run: the W8D2 subject is
  uncommitted and push/PR mutation was not authorized.

## Ordered remediation handoff

1. Human: explicitly approve remediation for `VDDAI-REV-001`; this review does
   not authorize implementation.
2. Coder: implement only the digest-reference validation and focused tests
   required by `VDDAI-REV-001`, preserving all approved W8D2 boundaries.
3. Coder: return a remediation report containing closure evidence. Do not
   commit, push, publish, deploy, merge, or promote.
4. Reviewer: create a numbered re-review and verify `VDDAI-REV-001` closure
   before QA begins.

## Residual risks and assumptions

- The temporary `ecdsa==0.19.2` exception is an explicitly human-approved risk
  only for `PYSEC-2026-1325` / `GHSA-wj6h-64fc-37mp` / `CVE-2024-23342`, while
  VDDAI remains HS256-only. It is not acceptance of other findings and becomes
  invalid if the JWT or crypto architecture changes.
- The Coder's current local image has labels for committed base
  `4772a05971b033dde39dadcc7b5cf35676094f33`, while the W8D2 working tree is
  uncommitted. It validates label plumbing, not final task-revision provenance.
  An authorized commit/push and hosted successful gate are required before any
  publication or release claim.
