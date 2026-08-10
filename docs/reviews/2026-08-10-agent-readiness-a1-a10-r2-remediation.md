# Agent-Readiness A1-A10 R2 Remediation Record

- Remediation date: 2026-08-10
- Source re-review: `docs/reviews/2026-08-10-agent-readiness-a1-a10-r2.md`
- Source verdict: `CHANGES REQUIRED`
- Finding addressed: `VDDAI-REV-006`
- Repository base: `origin/master` at `49a5b58c018602adfcf394c336528aec2cc13810`
- Branch: `chore/agent-readiness-a1-a10`
- Commit, push, merge, deployment, and model promotion: not performed

## VDDAI-REV-006 Disposition

- Original severity: `MEDIUM`
- Remediation status: `ADDRESSED — INDEPENDENT R3 REVIEW REQUIRED`
- Changed file: `docs/data_to_model_pipeline.md`

The maintained data-lineage document now describes the active Week 5 contracts:

- offline artifact generation and online package-backed inference are connected
  by the same storage-level preprocessing contract;
- `TorchManifestDataset` is a thin tensor adapter and preserves finite
  `torch.float32` image values in `[0, 1]`;
- `ResNet18FeatureExtractor` owns ImageNet mean/std normalization and applies it
  exactly once immediately before the frozen backbone;
- the split-aware DataLoader uses seeded training shuffles while validation and
  test preserve manifest order;
- the production worker calls `AnomalyInferenceService`, which preprocesses the
  stored upload, extracts a 512-dimensional feature, scores it against the
  package feature bank, and applies the frozen validation threshold;
- successful jobs atomically persist the package ID, anomaly score, threshold,
  label, latency, and public-safe package lineage;
- the server-controlled image path remains internal;
- the compatibility-only `confidence` field remains `null`, and anomaly distance
  is represented only by `anomaly_score`.

The executable contracts were not changed to match the stale documentation.

## Focused Closure Evidence

The revised document was compared against:

- `ml/data/torch_dataset.py`;
- `ml/data/torch_dataloader.py`;
- `ml/feature_extractor.py`;
- `app/services/anomaly_inference_service.py`;
- `app/workers/prediction_worker.py`;
- ADR 0003, ADR 0004, and ADR 0005.

Focused text validation confirmed that the document no longer contains:

- a `mock_model_service` production-serving claim;
- dataset-adapter ImageNet normalization;
- a statement that DataLoader image tensors leave `[0, 1]`;
- a future-tense claim that real serving is not connected;
- ambiguous `confidence or anomaly score` terminology.

It positively confirms extractor-owned normalization, split-aware ordering,
package-backed serving, persisted public-safe lineage, and compatibility-only
null confidence.

## Full Verification Evidence

`powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify.ps1 -IncludeDockerConfig`
passed with:

- Python `3.14.3`;
- pip `26.1.2`;
- all 73 exact `requirements.txt` pins;
- `pip check` with no broken requirements;
- 208 passing tests;
- valid Docker Compose configuration.

`git diff --check` also passed. Formatting was not included because the
repository documents pre-existing Black baseline drift and no Python file was
changed.

## R3 Review Handoff

Run a fresh independent review against the current branch and write:

`docs/reviews/2026-08-10-agent-readiness-a1-a10-r3.md`

The reviewer must preserve IDs `VDDAI-REV-001` through `VDDAI-REV-006`, verify
the revised documentation against the implementation and ADR sources above,
check the complete A1-A10 workspace, and issue a new final verdict. The reviewer
must not modify implementation, remediation, or prior review files.
