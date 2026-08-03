# ADR 0004 — Production Model-Package Loader

- Status: Accepted
- Date: 2026-08-03
- Contract: `vddai.production_inference.v1`

## Decision

Production selects one promoted Week 4 package through two explicit settings:

- `MODEL_PACKAGE_MANIFEST_PATH` points to that run's `run_manifest.json`;
- `FEATURE_BANK_DIR` points to its normal-training feature-bank directory.

No timestamp scan or "newest run" selection is permitted. The loader follows
the threshold member declared by the run manifest and cross-validates the
configured feature bank against both the manifest and threshold lineage.

The expected generated layout is:

```text
artifacts/
  evaluations/<promoted-run>/
    run_manifest.json
    threshold.json
  feature_banks/<promoted-bank>/
    metadata.json
    features.npz
```

The frozen `IMAGENET1K_V1` checkpoint remains a provisioned runtime dependency
in the local PyTorch checkpoint cache. It is never downloaded by the loader.
Its published filename hash is verified before `torch.load(weights_only=True)`.
Generated manifests, thresholds, banks, datasets, and weights remain outside
Git.

## Validation Boundary

Before returning anything, `ModelPackageLoader` validates:

- manifest, threshold, and feature-bank schema/code versions;
- package-relative threshold and feature archive paths, including symlink/path
  escape protection;
- promoted threshold and feature archive SHA-256 checksums;
- MVTec AD `tile` dataset version and manifest fingerprint consistency;
- normal-training-only bank and normal-validation-only threshold calibration;
- 224x224 preprocessing, frozen ResNet-18 identity, ImageNet normalization
  ownership, `avgpool`, and 512-dimensional features;
- a finite threshold, exact Euclidean mean-k-nearest scorer, positive `k` no
  larger than the bank, higher-is-more-anomalous direction, and strict
  `score > threshold` semantics;
- agreement between run manifest, threshold, feature-bank metadata, archive,
  and the W5D1 typed lineage contract.

Only after all artifact validation succeeds does the loader initialize the
scorer and frozen evaluation-mode extractor. It returns a frozen
`ProductionModelPackage` containing the runtime extractor, ready scorer,
threshold, stable package ID, and public-safe lineage.

## Process Lifecycle and Failures

`get_production_model_package()` uses a one-entry process cache. The worker
loads the package lazily for its first claimed job and reuses that exact object
for subsequent jobs; individual requests never reload artifacts. Cache reset
is guarded to the test environment.

Failures are reported as specific model-package artifact, checksum,
compatibility, or initialization errors. Messages identify the invalid package
member without exposing a fallback value. A failure returns no partial package
and never selects a mock, default threshold, random weights, regenerated
artifact, or network download.
