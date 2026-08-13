# W6D1 Reproducible Real-Inference Gate Review

- Review ID: `VDDAI-W6D1-INFERENCE-REVIEW-2026-08-12`
- Date: 2026-08-12
- Branch: `test/w6-inference-integration`
- Base commit: `9ffcf4d`
- Reviewed state: uncommitted working tree changes for W6D1
- Verdict: **PASS**

## Scope

This review covers the W6D1 implementation that turns the existing Week 5
production inference path into a reproducible integration gate. The reviewed
scope is the Docker runtime, authentication wiring needed by the deployed
flow, the live-stack proof script, the marked W6D1 regression suite, and the
operator documentation.

The review report itself is excluded from the implementation scope.

## Contract Sources

- Notion: [W6D1 — Integration Test: Real Model in Backend](https://app.notion.com/p/3ac0ab50ef6781759af4fb7e8786d4f8)
- Repository and application `AGENTS.md` instructions
- ADR-0003: production inference contract
- ADR-0004: artifact and package loading contract
- ADR-0005: prediction persistence contract
- Existing API, worker, package-loader, scorer, and preprocessing tests

## Acceptance Evidence

| Requirement | Evidence | Result |
| --- | --- | --- |
| Authenticated upload reaches the real package-backed worker and persisted readback | `scripts/prove_real_inference.py`; deployed Docker probe against API, PostgreSQL, worker, configured package, feature bank, and cached ResNet-18 weights | Pass |
| Invalid image is rejected | `test_create_prediction_rejects_invalid_image_bytes` in the W6 marker | Pass |
| Unavailable artifact fails closed | `test_unavailable_production_package_becomes_safe_failed_result` | Pass |
| Worker failure persists privately and returns a stable public failure | `test_worker_persists_failure` and `test_uploaded_image_preprocessing_failure_becomes_safe_failed_result` | Pass |
| Duplicate/retry does not rescore a terminal job | `test_completed_prediction_is_not_claimed_or_scored_twice` verifies one extractor call | Pass |
| Unauthorized and cross-owner reads remain non-disclosing | `test_get_prediction_hides_other_users_prediction`; the deployed probe verifies a second user receives `404` | Pass |
| Authentication works through the deployed application router | `test_registered_user_can_login_and_access_authenticated_predictions`; live OpenAPI exposes register and login routes | Pass |
| One-command Docker gate is documented | `docker compose exec api python -m pytest -q -m w6_inference_gate`; deployed proof command also documented | Pass |
| Model lineage and public response contract are preserved | Live probe validates score, threshold, label, latency, package ID, lineage, null confidence, and absence of private fields | Pass |

## Verification Results

- Local W6 marker: `10 passed, 23 deselected`.
- Probe validator tests: `4 passed`.
- Full local verification with Docker configuration validation: `222 passed`;
  Python 3.14.3, pip 26.1.2, exact requirements, dependency integrity,
  documentation validation, and Compose configuration all passed.
- Full Docker test suite: `222 passed`.
- Docker W6 marker: `10 passed, 212 deselected`.
- Deployed real-inference probe: passed with prediction ID `1`, package
  `mvtec-tile-resnet18-knn-fe64db2228370b2d`, anomaly score
  `13.027523040771484`, threshold `4.2167956829071045`, label `anomalous`, and
  latency `131 ms`.
- Docker dependency integrity: `No broken requirements found`.
- Docker runtime: pip `26.1.2`, torch `2.13.0+cpu`, torchvision
  `0.28.0+cpu`, with no installed CUDA/NVIDIA packages.
- Docker OpenAPI paths include `/auth/register`, `/auth/login`, and the
  prediction routes.
- Changed-file Black check and `git diff --check`: passed. Git emitted only
  expected working-tree line-ending conversion warnings.

## Findings

No actionable correctness, security, privacy, architecture, or release-gate
findings were identified in the reviewed W6D1 scope.

## Residual Risks and Assumptions

- The deployed proof intentionally creates two isolated development users, one
  prediction record, and one uploaded probe image in the target local stack.
  It does not perform destructive cleanup. Operators should run it against a
  disposable local or test environment, not a production database.
- The Week 4 package, feature bank, and Torch checkpoint are generated or
  provisioned runtime artifacts and remain ignored by Git. A fresh machine
  must provision them before running the deployed proof.
- Hosted CI was not run because this branch has not been committed or pushed.
- No database schema changed, so migration upgrade/downgrade testing beyond the
  normal Compose startup migration was not required.
- No model promotion, deployment, merge, commit, or push was performed.

## Release Recommendation

The W6D1 implementation is ready for human review and an intentional commit.
Production promotion and merge remain separate human-controlled actions.
