# ADR 0003 — Production Inference Contract v1

- Status: Accepted
- Date: 2026-08-01
- Contract schema: `vddai.production_inference.v1`
- Package schema: `vddai.inference_package.v1`
- Preprocessing schema: `vddai.preprocessing.rgb_chw_bilinear.v1`

## Context

Week 4 froze an image-level MVTec AD `tile` baseline. Online serving needs one
stable boundary between an authenticated upload, its server-controlled stored
file, the frozen artifacts, worker inference, persistence, and API readback.
The executable definitions live in `app/contracts/inference.py`.

## Input Boundary

The API authenticates the caller and stores a prediction owned by that user.
Serving accepts only the server-generated stored-image path; it never accepts a
client path. Before storage, the upload is size-limited, non-empty, decoded and
verified by Pillow, limited to JPEG/PNG/WebP, checked against its declared media
type, checked for positive dimensions, and saved under a UUID filename.

Deterministic online preprocessing is exactly:

1. decode the stored image;
2. apply EXIF transpose;
3. convert to RGB;
4. resize directly to 224x224 with Pillow bilinear resampling and no crop;
5. convert HWC to contiguous CHW NumPy `float32` in `[0, 1]`;
6. add the batch dimension, producing `(N, 3, 224, 224)` PyTorch `float32`.

Shared preprocessing does not apply ImageNet normalization. Channel-wise
ImageNet mean/std normalization remains owned by the frozen ResNet-18 adapter.

## Frozen Artifact Package Boundary

One package must identify all of the following before it can serve:

- contract, package, preprocessing, feature-bank, and threshold schema versions;
- stable package/model identifier derived from canonical frozen lineage;
- dataset name (`MVTec AD`), category (`tile`), dataset version, and manifest
  fingerprint;
- frozen `torchvision.resnet18` extractor, `IMAGENET1K_V1` weights, `avgpool`
  layer, and 512-dimensional output;
- package-relative feature-bank path, SHA-256 checksum, code/schema version,
  normal-training sample count, and training-only split identity;
- exact Euclidean mean-k-nearest scorer, configured positive `k`, and the fact
  that higher scores are more anomalous;
- finite threshold value, normal-validation-quantile policy and quantile, plus
  the threshold-artifact SHA-256 checksum.

These are frozen serving inputs. A request must never regenerate a feature
bank or threshold, retune `k`, download weights, or use official-test data.
Absolute filesystem paths are not public lineage and are never serialized.

## Decision Boundary

The anomaly score is an unbounded Euclidean distance, not a probability and not
confidence. Higher means more anomalous. Classification is immutable:

```text
score > threshold  -> anomalous
score <= threshold -> normal
```

Equality is therefore normal. The legacy public `confidence` key is retained
for response compatibility but is always `null`; `anomaly_score` is the only
score field.

## Output and Lifecycle Boundary

| Status | Result fields | Terminal fields |
|---|---|---|
| `queued` | All null | `created_at`; no completion or failure |
| `processing` | All null | `created_at`; no completion or failure |
| `completed` | label, anomaly score, threshold, latency, package ID, full public-safe lineage | `created_at`, `completed_at` |
| `failed` | All result fields null | `created_at`, `completed_at`, public `inference_failed` code |

`needs_review` remains a successful-result lifecycle extension and carries the
same result requirements as `completed`. Internal exception text stays in the
database/logging boundary for diagnosis but is not part of `PredictionRead`.
The API must not expose internal stack traces or filesystem paths.

## Compatibility and Failure Behavior

The Pydantic package model forbids unknown members and requires every lineage
member. The loader must fail closed before serving when an artifact is missing,
unreadable, corrupt, checksum-mismatched, outside its package directory,
schema-incompatible, test-derived, non-finite, or dimension-incompatible.
There is no mock, default-threshold, regeneration, or download fallback.

Any intentional semantic change requires a new contract/package/preprocessing
schema version. W5D2 artifact loading and W5D3 inference must import this
contract rather than redefine labels, score direction, threshold semantics,
lineage, or typed results.

## Consequences

- API consumers can distinguish an anomaly distance from probability.
- Package identity and result serialization drift fail during validation/tests.
- Public failures are stable and safe, while detailed errors remain internal.
- Existing persistence can retain the deprecated confidence column without
  assigning it a misleading serving meaning.
