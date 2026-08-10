# ADR 0002 — Anomaly Baseline and PyTorch Data Contract

- Status: Accepted; amended 2026-08-10
- Date: 2026-07-25

## Amendment — 2026-08-10

The baseline choice, split boundaries, threshold policy, and lineage intent
remain accepted. The active Week 4-5 implementation and ADR 0003 supersede two
earlier implementation details in this decision:

- dataset samples and DataLoader batches preserve the shared `[0, 1]` tensor
  contract; `ResNet18FeatureExtractor` owns and applies ImageNet normalization
  exactly once immediately before the frozen backbone;
- train-loader ordering uses deterministic seeded shuffling, while validation
  and official-test loaders preserve manifest order.

The updated contract and verification sections below incorporate this
amendment. Active code must not be changed back to the superseded adapter-owned
normalization or globally unshuffled loader behavior.

## Context

Week 3 established a deterministic MVTec AD tile dataset pipeline using
NumPy and Pillow. The pipeline produces fixed-shape images, labels,
segmentation masks, sample identifiers, and dataset lineage metadata.

Week 4 requires a real anomaly-detection baseline without redefining the
validated dataset semantics or introducing training-serving skew.

The initial MVTec training and validation splits contain only normal images.
The official test split contains both normal and defective images and must
remain isolated from model fitting and threshold selection.

## Decision

The first anomaly-detection baseline will use a frozen pretrained ResNet-18
as an image-level feature extractor.

Normal training images will form the reference embedding bank. Validation
images will be scored against that bank and used to establish an operational
anomaly threshold. Official test images will be used only for final
evaluation.

The initial anomaly score will measure distance from the learned normal
representation. The precise distance implementation will be established in
the next baseline milestone.

## Data Boundaries

- Training uses only normal images from the training manifest split.
- Validation uses only held-out normal training images.
- The anomaly threshold is selected without using official test labels.
- Official test images never influence the feature bank or threshold.
- Ground-truth masks are reserved for evaluation and qualitative analysis.
- Dataset versions and sample identifiers remain attached to model outputs.

## PyTorch Tensor Contract

The existing Week 3 preprocessing contract remains responsible for image
decoding, EXIF correction, RGB conversion, resizing, and conversion to a
contiguous NumPy float32 array in the range `[0, 1]`.

The PyTorch adapter converts validated NumPy samples to tensors without adding
image preprocessing or model-specific normalization:

```text
images:    (N, 3, H, W), torch.float32
labels:    (N,), torch.int64
masks:     (N, 1, H, W), torch.uint8
has_masks: (N,), torch.bool
```

Dataset samples and DataLoader batches remain finite and in `[0, 1]`. The
frozen `ResNet18FeatureExtractor` validates that input contract and applies
ImageNet normalization internally using:

```text
mean: (0.485, 0.456, 0.406)
std:  (0.229, 0.224, 0.225)
```

The normalized tensor is internal to the extractor and is passed directly to
the frozen backbone. It is not stored back into the dataset sample or batch.

## Determinism

- Manifest ordering is preserved for validation and official-test loaders.
- The training loader uses deterministic seeded shuffling.
- Python, NumPy, PyTorch, the DataLoader generator, and worker processes receive
  deterministic seeds.
- The default DataLoader configuration uses `num_workers=0` and random seed
  `42`; callers may configure worker count without weakening seeded execution.
- No random augmentation is used in the first baseline.
- Tensor batches retain sample IDs and source metadata.
- CPU execution is the initial reproducibility reference.

## Threshold Policy

- Because the validation split contains only normal images, it cannot support
  supervised threshold optimization.
- The initial operational threshold will be the 95th percentile of validation
  anomaly scores. This represents a target false-positive rate rather than an
  F1-optimal threshold.
- ROC-AUC and average precision will be calculated from continuous scores on
  the official test split. Precision, recall, F1, and false-positive rate will
  also be reported at the fixed validation threshold.

## Consequences

### Positive

- The validated Week 3 dataset semantics remain unchanged.
- Model-specific normalization is isolated inside the frozen extractor.
- Test leakage is prevented by construction.
- Every tensor batch remains traceable to manifest records.
- The baseline can be reproduced on CPU.
- Future feature extractors can reuse the same adapter boundary.

### Negative

- A normal-only validation split cannot estimate anomaly recall.
- The 95th-percentile threshold is operational rather than performance
- optimal.
- CPU feature extraction will be slower than GPU execution.
- A global image embedding does not provide pixel-level anomaly localization.
- Pretrained ImageNet features may not represent all tile defects well.

## Verification

- The PyTorch adapter is covered for tensor shapes, dtypes, contiguous layout,
  metadata preservation, and invalid input rejection.
- The split-aware DataLoader is covered for seeded train ordering,
  validation/test manifest ordering, worker seeding, and invalid configuration.
- The frozen extractor is covered for `[0, 1]` input validation, exactly-once
  ImageNet normalization, frozen parameters, and 512-dimensional output.

Then run:

```powershell
.\scripts\verify.ps1
```
