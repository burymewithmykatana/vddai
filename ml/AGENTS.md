# VDDAI ML Instructions

These instructions extend the repository-root `AGENTS.md` for every change
under `ml/`. The root mission, human approval gates, Git rules, verification
requirements, and frozen production inference invariants still apply.

## ML Boundary

`ml/` owns the offline, reproducible image-anomaly pipeline:

```text
validated MVTec AD tile data
  -> deterministic manifest and split lineage
  -> shared image preprocessing
  -> frozen ResNet-18 features
  -> normal-training feature bank
  -> validation/test anomaly scores
  -> normal-validation threshold
  -> one frozen official-test evaluation
  -> descriptive error analysis
  -> versioned artifacts eligible for controlled registration
```

Keep data preparation, representation, scoring, calibration, evaluation, and
artifact generation separate. A command that performs one stage must not
silently tune or rerun another stage.

## Current and Legacy Modules

The active Week 3-5 image pipeline uses:

- `data/`: MVTec validation, deterministic manifests, dataset loading, masks,
  batches, and seeded DataLoaders;
- `feature_extractor.py`: frozen torchvision ResNet-18 adapter;
- `generate_feature_bank.py`: normal-training reference-bank generation;
- `anomaly_scorer.py` and `score_anomalies.py`: exact nearest-neighbor scoring
  and score-artifact generation;
- `threshold_selector.py` and `select_threshold.py`: normal-validation quantile
  calibration;
- `evaluation.py` and `evaluate_baseline.py`: frozen official-test image-level
  evaluation;
- `error_analysis.py` and `generate_error_analysis.py`: post-prediction,
  descriptive review artifacts.

Two older files are not authoritative for the production anomaly pipeline:

- `preprocessing.py` is a standalone earlier contract that center-crops and
  applies ImageNet normalization. The active manifest, feature-bank, scoring,
  evaluation, and serving paths instead use
  `app.services.image_preprocessing_service` for shared storage-level
  preprocessing and apply ImageNet normalization inside the ResNet adapter.
  Do not wire the older function into the active pipeline without an explicit,
  versioned preprocessing decision.
- `train_baseline.py` trains a scikit-learn breast-cancer classifier and writes
  the legacy tracked `artifacts/model.joblib` and `artifacts/metrics.json`.
  It is not the MVTec anomaly baseline, a production package, or a model
  promotion candidate. Do not extend or promote it unless a task explicitly
  addresses the legacy scaffold.

When current documentation, active imports, and a legacy module differ, follow
the executable Week 3-5 contracts and report the legacy discrepancy rather
than merging the behaviors.

## Dataset and Split Integrity

The reference dataset is MVTec AD `tile`.

- Raw `train/good` images are the only source for the development `train` and
  `validation` splits.
- The deterministic split uses the recorded seed and validation ratio.
- Feature-bank fitting accepts normal `train` records only.
- Threshold selection accepts normal `validation` records only.
- The official MVTec `test` split remains intact and is used only after the
  method, scorer, `k`, and threshold policy are frozen.
- Official-test labels and masks must not influence preprocessing, feature
  extraction, model/scorer selection, hyperparameters, `k`, threshold policy,
  quantile, or promotion criteria.

Stable sample IDs, relative source paths, split assignments, labels, defect
classes, image metadata, and mask associations are part of dataset lineage.
Manifest records must remain mutually disjoint across splits. Reject absolute
paths, dataset-root traversal, duplicate identities, missing samples, invalid
labels, corrupt files, unsupported formats, and inconsistent mask mappings.

Generated manifest JSON/CSV files are deterministic outputs. Dataset identity
is the canonical SHA-256 fingerprint of the manifest records and configuration;
do not replace it with a directory timestamp, mutable display name, or row
count.

## Image and Mask Contracts

The active shared image contract is implemented by
`app.services.image_preprocessing_service`:

- apply EXIF orientation;
- convert to RGB;
- resize directly to the configured exact size using bilinear interpolation;
- do not crop;
- produce contiguous CHW NumPy `float32`;
- keep values finite and in `[0, 1]`;
- default to shape `(3, 224, 224)`.

ImageNet channel normalization is model-specific and belongs inside
`ResNet18FeatureExtractor`; it must not be moved into the shared storage-level
contract. Do not normalize twice.

Segmentation masks use nearest-neighbor resizing, explicit binary values, and
shape `(1, H, W)`. Normal samples receive an all-zero fixed-shape mask and an
explicit false mask-presence flag. Do not apply RGB interpolation or ImageNet
normalization to masks.

Any change to size, interpolation, crop policy, orientation, color space,
layout, dtype, numeric range, normalization ownership, or mask semantics is a
versioned compatibility change. Update online/offline tests together and
identify every artifact that must be regenerated.

## Reproducibility Claims

Record and reuse effective seeds. Current DataLoader construction seeds Python,
NumPy, PyTorch, the loader generator, and worker processes. Training loader
order is seeded; validation and test preserve manifest order.

Do not overstate determinism. The current contract proves deterministic split
assignment, manifest output, sample ordering, configuration, and artifact
lineage. It does not promise bitwise-identical outputs for every PyTorch CPU or
GPU kernel, device, driver, or library version. If stronger determinism is
required, define and test the additional runtime constraints explicitly.

## Frozen Feature Extractor

The Week 4 representation contract is:

- `torchvision.resnet18`;
- `IMAGENET1K_V1` / torchvision default ResNet-18 weights;
- classifier removed;
- `avgpool` output;
- 512-dimensional image-level features;
- all parameters frozen;
- evaluation and inference mode;
- input batches shaped `(N, 3, H, W)`, `torch.float32`, finite, in `[0, 1]`;
- ImageNet mean/std normalization applied once inside the adapter.

Do not fine-tune, unfreeze, replace the backbone, change the layer or dimension,
or add patch-level/spatial features as an in-place modification of the frozen
baseline. Those are new experiments with new lineage, artifacts, validation,
and compatibility consequences.

Offline artifact generation and production serving have different weight
provisioning contexts. Production serving must retain the fail-closed,
local-cache-only behavior defined under `app/`; do not infer that an offline
torchvision workflow authorizes serving-time downloads.

## Feature-Bank Rules

The reference feature bank contains only normal training samples. Preserve:

- row alignment among features, sample IDs, relative paths, splits, and dataset
  versions;
- finite two-dimensional feature data with exactly 512 columns;
- non-empty unique sample identities;
- training-only split metadata;
- dataset version and manifest fingerprint;
- extractor name, weights, layer, dimension, preprocessing, and seed;
- schema/code versions and the feature archive checksum;
- atomic replacement of completed artifact members.

Never insert validation or official-test features into the reference bank.
Changing the dataset, preprocessing, extractor, dimension, or bank composition
invalidates dependent score, threshold, evaluation, and serving artifacts.

## Scoring Rules

The frozen scorer computes exact Euclidean distance to the normal feature bank
and returns the mean of the configured `k` nearest distances. `k=1` is ordinary
nearest-neighbor distance. Scores are finite, unbounded anomaly distances;
higher means more anomalous.

Score generation processes validation and test records in the required stable
order and records labels for later calibration/evaluation. It must not select a
threshold, calculate final evaluation metrics, modify the bank, or tune `k`
using official-test outcomes.

A scorer or `k` change creates a new experiment and invalidates downstream
threshold and evaluation artifacts. Preserve scorer configuration and bank
checksum lineage in every score artifact.

## Threshold Rules

The frozen calibration policy is the configured linear quantile of normal
validation scores only. It is not optimized for F1, ROC-AUC, average precision,
accuracy, precision, recall, or official-test performance.

Reject empty, non-finite, misaligned, anomalous, or non-validation calibration
records. Preserve the quantile, linear interpolation method, validation sample
count, score summary, estimated validation false-positive rate, score-artifact
checksum, and complete upstream lineage.

Classification remains strict: `score > threshold` is anomalous and equality
is normal. Import or mirror the frozen contract deliberately; do not introduce
an inconsistent comparison in offline evaluation.

## Evaluation and Error Analysis

Freeze the method before inspecting official-test metrics. A complete
evaluation must verify training-only bank lineage, select the threshold from
normal validation records, and calculate final image-level metrics from the
official test records without retuning.

Use continuous scores in their original higher-is-more-anomalous direction.
Preserve ROC-AUC, the full precision-recall data, non-interpolated average
precision, thresholded confusion/rate metrics, per-defect summaries, sample
rows, configuration, checksums, and the run manifest.

Named evaluation runs fail if the destination exists unless overwrite is
explicitly requested through the existing run policy. Do not silently reuse,
merge, or overwrite a prior run. An explicit overwrite is a reproducible local
artifact action, not production model promotion.

Error analysis is descriptive and post-prediction. Ground-truth masks may
annotate and rank TP/TN/FP/FN cases and describe anomaly area, but they must not
be used to retune the completed baseline. Spatial localization, heatmaps,
pixel-level predictions, connected-component models, and patch-based anomaly
methods are not capabilities of the current image-level baseline.

## Artifact and Schema Rules

Generated manifests, reports, feature banks, scores, thresholds, evaluation
runs, plots, model weights, and error-analysis outputs remain outside Git unless
a task explicitly requests a small reviewed fixture.

For every versioned artifact:

- use explicit schema and code versions;
- use canonical, deterministic serialization where identity depends on bytes;
- record upstream artifact identity and checksums;
- use package-relative paths where artifacts reference members;
- validate completeness before exposing the artifact;
- write through temporary siblings and replace atomically where the existing
  generator provides that guarantee;
- fail on malformed, incompatible, misaligned, non-finite, or lineage-incomplete
  input.

An artifact schema change requires compatibility analysis, contract tests,
documentation, and a list of invalidated/regenerated downstream artifacts. Do
not silently accept unknown schema versions or backfill missing lineage with
guesses.

## Week 6 Experiment Tracking

Week 6 must make each training/evaluation attempt independently auditable.
Experiment records should preserve an immutable experiment/run ID, dataset
version and manifest fingerprint, code revision, effective parameters and seed,
preprocessing/extractor/scorer/threshold configuration, metrics, artifact
locations and checksums, schema/code versions, timestamps, and terminal status.

Keep these concepts distinct:

- an experiment records what was attempted and observed;
- a candidate registration identifies a complete validated package;
- a promotion decision changes an auditable registry state;
- serving resolves only the explicitly promoted production package.

Failed experiments remain evidence and must not masquerade as successful
candidates. Registration must not imply promotion. An agent may implement and
test registration/promotion mechanics, but only a human may approve a real
production promotion or rollback.

Promotion criteria must be declared before consulting the candidate's official
test outcome when test-set isolation would otherwise be compromised. Never
turn repeated official-test comparison into an informal model-selection loop.

## Focused Verification

Useful existing test groups include:

```powershell
python -m pytest -q app/tests/test_dataset_manifest.py app/tests/test_manifest_processing.py app/tests/test_torch_dataset.py app/tests/test_torch_dataloader.py
python -m pytest -q app/tests/test_feature_extractor.py app/tests/test_feature_bank.py
python -m pytest -q app/tests/test_anomaly_scorer.py app/tests/test_score_anomalies.py
python -m pytest -q app/tests/test_threshold_selector.py app/tests/test_select_threshold.py
python -m pytest -q app/tests/test_evaluation.py app/tests/test_evaluate_baseline.py
python -m pytest -q app/tests/test_error_analysis.py app/tests/test_generate_error_analysis.py
```

When a change crosses artifact or serving boundaries, also run the relevant
package-loader, inference-contract, and inference-service tests under `app/tests`.
Focused tests do not replace the applicable repository-wide verification in the
root instructions.

Do not run full dataset generation, feature extraction, evaluation, or artifact
regeneration merely to validate an instruction-only change. For real ML changes,
state which commands and local data/artifacts are required before running them,
and never claim a generated result that was not produced.

## Code Review Rules

Treat these as high-priority findings in `ml/` changes:

- train, validation, and official-test roles are mixed or test outcomes affect
  development choices;
- the active pipeline switches to the legacy preprocessing or tabular baseline;
- offline preprocessing diverges from the online storage-level contract;
- model normalization is omitted, duplicated, or moved to the wrong layer;
- feature banks contain non-training or anomalous samples;
- row alignment, fingerprints, checksums, schema versions, or lineage are lost;
- a threshold is optimized on labels or official-test performance;
- score direction or strict threshold equality semantics change;
- an evaluation or report silently overwrites an existing run;
- deterministic behavior is claimed beyond the tested seed/order boundary;
- a new experiment mutates the frozen baseline in place;
- registration is treated as promotion or promotion bypasses human approval.

For each finding, identify the contaminated split or broken lineage boundary,
the downstream artifacts affected, and the safe regeneration or versioning
path.
