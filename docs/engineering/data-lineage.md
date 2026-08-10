# Project Data Lineage

- Status: Current
- Last reviewed: 2026-08-10
- Scope: MVTec AD `tile` offline lineage and package-backed online inference

This document is the project data lineage explanation. It describes where the
MVTec AD tile data comes from, how each processing stage transforms it, which
identifiers are preserved, and how model-facing tensors can be traced back to
the original dataset files.

## Current Scope

The repository has two connected model-related contexts:

- The offline MVTec AD image pipeline builds deterministic manifests, frozen
  feature banks, validation thresholds, evaluation records, and versioned model
  packages.
- The production API stores authenticated uploads and the prediction worker
  scores each stored image with one explicitly configured, frozen model package.
  Completed rows persist the decision inputs and public-safe package lineage.

Both contexts use the same storage-level image preprocessing contract. The
offline path additionally preserves manifest sample lineage, while online
serving preserves prediction and model-package lineage.

## Lineage Overview

```text
Raw source files
  data/raw/mvtec_ad/tile
    -> Dataset validation
       ml/data/validate_mvtec.py
    -> Deterministic manifest
       ml/data/build_manifest.py
    -> NumPy dataset samples
       ml/data/dataset.py + ml/data/process_manifest.py
    -> PyTorch dataset samples
       ml/data/torch_dataset.py
    -> DataLoader batches
       batch.images + labels + masks + lineage metadata
    -> Model scoring / training
       feature extractor and anomaly scoring baseline
```

The core lineage keys are:

- `image_path`: stable source path relative to the dataset root;
- `sample_id`: stable SHA-256 based identifier derived from `image_path`;
- `dataset_version`: SHA-256 hash of the canonical manifest records;
- `split`: records whether the sample belongs to `train`, `validation`, or
  `test`;
- `mask_path`: links anomalous test images to their ground-truth masks.

## 1. Source Dataset

Dataset constants live in `ml/data/mvtec_contract.py`.

- `DATASET_ROOT` points to `data/raw/mvtec_ad/tile`.
- The expected MVTec directory layout is:
  - `train`
  - `test`
  - `ground_truth`

For the tile category, normal training images are expected under
`train/good`, official test images are expected under `test/<class_name>`, and
defect masks are expected under `ground_truth/<defect_type>`.

At this point, the project has not transformed the images. The source lineage
anchor is the relative file path under `DATASET_ROOT`.

## 2. Validation Lineage

`ml/data/validate_mvtec.py` validates the raw dataset before any manifest or
model input is built.

It checks:

- required directories exist;
- files have supported image suffixes;
- images can be opened and verified by Pillow;
- image dimensions, modes, and formats can be inspected;
- `ground_truth` files are treated as masks;
- each defective test image has the expected mask path;
- masks without matching defective test images are reported as orphan masks.

The validation output includes counts by split, class, image size, format, and
mode. Integrity problems are surfaced as corrupt files, unsupported files, or
mask association errors.

The validation stage creates `ImageRecord` and `MaskAssociation` objects. These
objects are not yet the training manifest; they are the inspected source
inventory used to decide whether the dataset is safe to consume.

Validation lineage fields include:

- `path`: source-relative file path;
- `split`: inferred from the first path segment;
- `class_name`: inferred from the second path segment;
- `record_type`: `image` or `mask`;
- `width`, `height`, `mode`, `image_format`: inspected source metadata.

## 3. Manifest Lineage

`ml/data/build_manifest.py` turns the validated dataset into a deterministic
manifest.

The manifest records one row per model input image and includes:

- `sample_id`: stable SHA-256 based identifier derived from the relative image
  path;
- `image_path`: path relative to the dataset root;
- `split`: `train`, `validation`, or `test`;
- `label`: `0` for normal and `1` for anomaly;
- `class_name`: MVTec class folder, such as `good`, `crack`, or `glue_strip`;
- `is_anomaly`: boolean version of the label;
- `mask_path`: relative mask path for anomalous test samples, otherwise
  `null`;
- original image metadata: width, height, format, and mode.

The split policy is intentional:

- `train` is built only from official `train/good` images;
- `validation` is a deterministic holdout from official `train/good`;
- `test` is the official MVTec test split and contains both normal and
  anomalous samples.

The default validation ratio is `0.2`, and the default random seed is `42`.
The manifest also stores a `dataset_version`, calculated as a SHA-256 hash of
the canonical manifest records.

This is the first durable project-level lineage artifact. Every downstream
sample should be traceable back to one manifest record by `sample_id` and
`image_path`.

Generated files are written under `data/metadata`, including:

- `mvtec_ad_tile_manifest.generated.json`
- `mvtec_ad_tile_manifest.generated.csv`

## 4. Preprocessing Lineage

Image preprocessing is implemented in
`app/services/image_preprocessing_service.py` and reused by the dataset code.

For each image, the service:

1. opens the file with Pillow;
2. applies EXIF orientation correction;
3. converts the image to RGB;
4. resizes it to the configured model size;
5. converts pixels to `np.float32`;
6. scales values from `[0, 255]` to `[0, 1]`;
7. transposes layout from HWC to CHW;
8. returns a C-contiguous array.

The default model size comes from `app/core/config.py`:

```text
MODEL_IMAGE_WIDTH=224
MODEL_IMAGE_HEIGHT=224
```

The resulting image contract is:

```text
shape: (3, 224, 224)
dtype: np.float32
range: [0, 1]
layout: CHW
memory: C-contiguous
```

`ml/data/process_manifest.py` wraps this preprocessing for a manifest record.
It also protects the dataset boundary by rejecting absolute paths, paths that
escape the dataset root, missing image files, invalid dtypes, invalid channel
counts, non-contiguous arrays, and out-of-range pixel values.

The preprocessing output keeps enough lineage to relate the transformed tensor
to the original image:

- `sample_id`: copied from the manifest record;
- `source_path`: copied from `image_path`;
- `original_width` and `original_height`: captured before resizing;
- `split`, `label`, `class_name`, and `is_anomaly`: copied from the manifest.

## 5. Sample and Mask Lineage

`ml/data/dataset.py` exposes `ManifestDataset`, a sequence of
`DatasetSample` objects for one split.

For each manifest record:

- the image is loaded through `process_manifest_record`;
- anomalous samples must have a mask;
- normal samples must not have a mask;
- masks are opened as grayscale images;
- masks are resized with nearest-neighbor interpolation;
- masks are thresholded to binary values;
- masks are expanded to shape `(1, H, W)`.

Normal samples receive an all-zero mask with `has_mask=False`. Anomalous
samples receive the processed ground-truth mask with `has_mask=True`.

The NumPy sample contract is:

```text
image:    (3, H, W), np.float32, values in [0, 1]
label:    int, 0 normal / 1 anomaly
mask:     (1, H, W), np.uint8, values in {0, 1}
has_mask: bool
```

`collate_samples` stacks samples into a `DatasetBatch`:

```text
images:    (N, 3, H, W), np.float32
labels:    (N,), np.int64
masks:     (N, 1, H, W), np.uint8
has_masks: (N,), np.bool_
```

Metadata such as `sample_ids`, `source_paths`, and `class_names` is preserved
alongside the arrays.

This stage is where mask lineage is enforced:

- anomalous samples must point to an existing `mask_path`;
- normal samples must not carry a `mask_path`;
- normal samples receive generated zero masks, marked with `has_mask=False`;
- anomalous samples receive processed ground-truth masks, marked with
  `has_mask=True`.

## 6. Tensor Lineage

`ml/data/torch_dataset.py` converts the NumPy dataset contract into PyTorch
tensors.

`TorchManifestDataset` wraps a `ManifestDataset`. Each sample conversion:

- converts the contiguous NumPy image into a `torch.float32` tensor without
  redefining image preprocessing;
- preserves the shared finite `[0, 1]` image-value contract;
- converts the label to `torch.int64`;
- converts the mask to contiguous `torch.uint8`;
- converts `has_mask` to `torch.bool`;
- preserves sample metadata.

ImageNet normalization is not applied by `TorchManifestDataset` or the
DataLoader. `ResNet18FeatureExtractor` validates the batched `[0, 1]` tensor and
applies the following model-specific normalization exactly once immediately
before the frozen backbone:

```text
mean: (0.485, 0.456, 0.406)
std:  (0.229, 0.224, 0.225)
```

The normalized tensor is internal to the feature extractor. Dataset samples and
DataLoader batches remain in `[0, 1]`.

`create_split_dataloader` builds a split-aware PyTorch `DataLoader` with:

- seeded shuffling for the `train` split;
- manifest order preserved for `validation` and `test`;
- Python, NumPy, PyTorch, DataLoader-generator, and worker seeds derived from
  the configured random seed, which defaults to `42`;
- configurable `num_workers`, `pin_memory`, and `drop_last`, whose defaults are
  `0`, `False`, and `False`;
- custom collation through `collate_torch_samples`.

The model-facing PyTorch batch contract is:

```text
images:    (N, 3, H, W), torch.float32
labels:    (N,), torch.int64
masks:     (N, 1, H, W), torch.uint8
has_masks: (N,), torch.bool
```

The batch also carries:

```text
sample_ids
splits
source_paths
class_names
mask_paths
```

This metadata lets model outputs be traced back to the exact manifest records
and source files.

At this stage, image values still use the shared storage-level `[0, 1]`
contract. Model-specific normalization occurs only inside the feature extractor,
while lineage remains carried as plain metadata fields outside the tensors.

## 7. Model Lineage

The intended anomaly baseline, documented in
`docs/decisions/0002-anomaly-baseline-and-pytorch-data-contract.md`, uses a
frozen pretrained ResNet-18 as a feature extractor.

The frozen artifact and evaluation flow is:

1. Build the manifest from the validated dataset.
2. Create a `ManifestDataset` for the `train` split.
3. Wrap it with `TorchManifestDataset`.
4. Create a `DataLoader`.
5. Feed `batch.images` into the feature extractor.
6. Store normal-image embeddings as the reference bank.
7. Score validation images against the reference bank.
8. Set the operational threshold from validation scores.
9. Evaluate official test images without using them during training or
   threshold selection.

Ground-truth masks are not needed to train the first image-level baseline.
They are preserved for evaluation, reporting, and future localization work.

Expected model outputs should preserve the following lineage fields whenever
scores, predictions, embeddings, or evaluation rows are written:

- `dataset_version`;
- `sample_id`;
- `source_path`;
- `split`;
- `class_name`;
- `label`;
- `is_anomaly`;
- `mask_path`, when available;
- model version or artifact identifier;
- threshold version or threshold value, when producing binary predictions.

Keeping these fields attached makes it possible to answer: which raw image
produced this score, which manifest version it came from, which split it
belonged to, and which model artifact produced the result.

## 8. Reproducibility Report

`ml/data/report.py` runs the complete dataset pipeline and writes a
reproducibility report to:

```text
data/metadata/mvtec_ad_tile_pipeline.generated.json
```

The report verifies:

- dataset integrity;
- manifest counts;
- split and class distributions;
- anomaly counts;
- mask counts by split;
- preprocessing dimensions;
- NumPy batch shape and dtype contracts.

Use this command to regenerate the pipeline report:

```bash
python -m ml.data.report
```

Use this command to rebuild the manifest:

```bash
python -m ml.data.build_manifest
```

## 9. Serving Lineage Status

The production API path is package-backed:

1. `app/api/routes/prediction.py` authenticates the caller, validates and stores
   the upload under a server-controlled path, and creates an owner-scoped queued
   prediction row.
2. `app/workers/prediction_worker.py` claims the oldest queued row with a
   database lock, transitions it to processing, and calls
   `AnomalyInferenceService`.
3. `app/services/anomaly_inference_service.py` applies the same shared
   storage-level preprocessing contract, passes the `[0, 1]` batch to the frozen
   ResNet-18 extractor, scores its 512-dimensional feature against the package's
   normal-training feature bank, and applies the frozen validation threshold.
4. The worker atomically persists the terminal label, anomaly score, threshold,
   package ID, latency, and complete public-safe model lineage.

Serving does not use `TorchManifestDataset` or a DataLoader because each job is
one stored upload rather than a manifest sample. Offline and online paths still
share preprocessing, feature-extractor, scorer, threshold, and package
compatibility contracts.

Completed prediction lineage includes:

- the prediction record ID, lifecycle timestamps, and safe upload metadata;
- preprocessing, inference-contract, and package schema identifiers;
- package ID in `model_version`;
- MVTec AD category, dataset version, and manifest fingerprint;
- ResNet-18 weights, feature layer, and feature dimension;
- feature-bank identity, metadata, and checksum;
- scorer configuration, score direction, and `k`;
- validation-threshold policy, value, and checksum;
- anomaly score, threshold, predicted label, and inference latency.

The server-controlled image path remains internal and is not exposed by the
public API. The legacy `confidence` field remains compatibility-only and is
always `null`; anomaly distance is represented only by `anomaly_score`.

## 10. Lineage Checkpoints

Use these checkpoints when debugging or auditing a prediction:

```text
Raw image
  image_path under DATASET_ROOT

Validated inventory
  ImageRecord.path, split, class_name, dimensions, format

Manifest record
  sample_id, dataset_version, label, mask_path

Processed sample
  source_path, original dimensions, CHW float32 image

Dataset sample
  image, label, mask, has_mask, class metadata

Torch sample
  [0, 1] image tensor, tensor label, tensor mask

Batch
  batch.images plus sample_ids/source_paths/class_names

Feature extractor
  adapter-owned ImageNet normalization, frozen 512-dimensional ResNet-18 feature

Model output
  anomaly score or label tied back to sample_id and dataset_version

Serving result
  prediction ID, package ID, anomaly score, threshold, label, latency,
  and public-safe package lineage
```

The invariant is simple: downstream outputs must never lose the ability to
trace back to the manifest record and raw source file that produced them.
