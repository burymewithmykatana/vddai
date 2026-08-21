# VDDAI Backend

Production-oriented backend for authenticated, asynchronous visual anomaly
detection. VDDAI is designed as a reusable pilot platform rather than a
detector tied to one product category.

> **Status:** Registry-selected production inference and W7D2 prediction
> reliability are complete in the proposed v0.1.0 working tree. Authenticated
> prediction jobs use bounded retries, attempt leases, stale-work recovery, and
> fenced terminal persistence while preserving the frozen MVTec AD `tile`
> inference and public API contracts.

## Start Here

| I want to... | Go to |
|---|---|
| Run the API on my machine | [Local development](#local-development-api-on-the-host) |
| Run the complete stack | [Docker development](#docker-development-all-services) |
| Configure the real model package | [Configuration](#configuration) and [Week 5 production inference](#week-5-production-inference) |
| Understand prediction retries and recovery | [Prediction reliability and recovery](#prediction-reliability-and-recovery) and [ADR 0010](docs/decisions/0010-database-backed-prediction-reliability.md) |
| Prove the complete inference flow | [W6D1 inference gate](#w6d1-reproducible-real-inference-gate) |
| Track and query the Week 4 baseline | [Week 6 experiment tracking](#week-6-experiment-tracking) |
| Reproduce the data and model baseline | [MVTec AD dataset](#mvtec-ad-tile-dataset) and [Week 4 baseline](#week-4-complete) |
| Understand image transformations | [Image preprocessing contract](#image-preprocessing-contract) |
| Navigate product, architecture, and engineering documentation | [Documentation index](docs/README.md) |
| Build or query local repository intelligence | [Graphify repository intelligence](docs/engineering/repository-intelligence.md) |
| Review limitations before deployment | [Known risks and deferred work](#known-risks-and-deferred-work) |

### Before Running Real Inference

Generated datasets, feature banks, evaluation runs, thresholds, and pretrained
weights are intentionally excluded from Git. The API and test suite can run
without committing those binaries, but the production worker fails closed
unless the configured Week 4 package and cached ResNet-18 weights are present.
See [Configuration](#configuration) for the required artifact paths.

The `.env.example` file uses Docker service names. If the API runs directly on
the host, change the database and Redis hosts to `localhost` as described in
[Local development](#local-development-api-on-the-host).

## What Works Today

| Area | Implemented capability |
|---|---|
| API and security | FastAPI health routes, JWT authentication, active-user checks, owner-scoped uploads, result readback, and history |
| Image storage | Opaque server-generated object keys, a backend-independent API/worker contract, and a traversal-safe local backend |
| Data contract | Validated MVTec AD `tile` ingestion, deterministic splits and fingerprints, mask handling, and shared offline/online preprocessing |
| Model baseline | Frozen ResNet-18 features, exact Euclidean nearest-neighbor scoring, and a validation-only frozen threshold |
| Production inference | Fail-closed package loading, checksum and lineage validation, worker-side inference, bounded retries, lease recovery, fenced lifecycle persistence, and safe failures |
| Verification | Canonical gate with 297 passing tests and 2 optional PostgreSQL tests, plus PostgreSQL 16 concurrency, restart-recovery, and migration QA |

## Project Goal

The target deliverable is a production-ready visual-inspection pilot that demonstrates:

- reproducible ML engineering;
- secure model-serving infrastructure;
- experiment and dataset traceability;
- deployment and monitoring;
- a credible customer pilot package;
- a portfolio case study suitable for international AI/ML engineering roles.

The platform remains domain-agnostic so it can be adapted to printing, ceramics, manufacturing, and other visual-inspection environments.

## Technology Stack

- Python 3.14.3
- FastAPI
- Pydantic v2
- SQLAlchemy 2
- PostgreSQL 16
- Redis 7
- Pillow
- NumPy
- scikit-learn
- Docker Compose
- pytest

## Repository Structure

```text
app/
├── api/                 # HTTP routes and API dependencies
├── core/                # Application configuration and security
├── db/                  # Database base, session, and initialization
├── models/              # SQLAlchemy persistence models
├── schemas/             # Request and response schemas
├── services/            # Model, storage, and preprocessing services
├── tests/               # API and service tests
└── main.py              # FastAPI application entry point

ml/                      # Training and ML pipeline code
docs/                    # Indexed product, architecture, engineering, ADR, review, and archive docs
scripts/                 # Bootstrap, verification, documentation, and operational utilities
artifacts/               # Generated model artifacts and metrics
uploads/                 # Default local image-object storage root
Dockerfile               # API container definition
docker-compose.yaml      # API, PostgreSQL, and Redis stack
requirements.txt         # Pinned Python dependencies
.env.example             # Development configuration template
```

## Optional Repository Intelligence

Graphify `0.9.47` can generate local, code-only structural evidence without
changing application dependencies or runtime behavior. Install it in an
isolated tool environment, then use the tracked wrapper:

```powershell
uv tool install graphifyy==0.9.47
graphify --version
python scripts/graphify_repository.py build
python scripts/graphify_repository.py validate
python scripts/graphify_repository.py affected classify_anomaly_score --depth 3
```

Generated `graphify-out/` files are ignored and Docker-excluded. Queries fail
closed when the graph is missing or stale. Graphify is optional derived
structural evidence; verify conclusions against direct repository sources.
See the full [repository intelligence contract](docs/engineering/repository-intelligence.md).

## Configuration

Create a working environment file from the provided template:

```powershell
Copy-Item .env.example .env
```

The template contains development defaults:

```env
PROJECT_NAME=vddai-backend
ENVIRONMENT=development

DATABASE_URL=postgresql+psycopg://postgres:postgres@postgres:5432/vision_ai
REDIS_URL=redis://redis:6379/0

JWT_SECRET_KEY=change-this-secret
JWT_EXPIRE_MINUTES=60

MAX_IMAGE_SIZE_MB=5
IMAGE_STORAGE_BACKEND=local
IMAGE_STORAGE_ROOT=uploads

MODEL_IMAGE_WIDTH=224
MODEL_IMAGE_HEIGHT=224
MODEL_DEVICE=cpu
WORKER_POLL_INTERVAL_SECONDS=1.0
WORKER_MAX_ATTEMPTS=3
WORKER_RETRY_DELAY_SECONDS=5.0
WORKER_ATTEMPT_LEASE_SECONDS=300.0
MODEL_REGISTRY_PATH=artifacts/registry/model_registry.sqlite3
MODEL_ARTIFACT_ROOT=.
```

Replace `JWT_SECRET_KEY` before running the application outside isolated local development. Never commit the real `.env` file.

`IMAGE_STORAGE_BACKEND=local` selects the currently implemented backend and
`IMAGE_STORAGE_ROOT` sets its development storage root. Predictions persist
opaque keys such as `predictions/<uuid>.png`; neither API clients nor workers
use that value as a host filesystem path. A shared object-store implementation
is intentionally deferred.

`WORKER_MAX_ATTEMPTS` counts the initial attempt and every retry.
`WORKER_RETRY_DELAY_SECONDS` is the fixed delay before a retry becomes
eligible, and `WORKER_ATTEMPT_LEASE_SECONDS` bounds one worker attempt. All
three values are process configuration; timing values must be finite and
positive, and the maximum must be a positive integer. Set the lease above the
expected worst-case inference duration so live work is not needlessly
reclaimed.

## Local Development: API on the Host

### Prerequisites

- Python 3.14.3
- Docker Desktop with Docker Compose
- Git

### 1. Create and activate a virtual environment

Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### 2. Install dependencies

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip check
```

### 3. Configure local service addresses

The values in `.env.example` use Docker service names. When the API runs directly on Windows, change these values in `.env`:

```env
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/vision_ai
REDIS_URL=redis://localhost:6379/0
JWT_SECRET_KEY=replace-with-a-secure-development-secret
```

### 4. Start PostgreSQL and Redis

```powershell
docker compose up -d postgres redis
```

Verify both services:

```powershell
docker compose exec postgres pg_isready -U postgres -d vision_ai
docker compose exec redis redis-cli ping
```

Expected results are `accepting connections` and `PONG`.

### 5. Start the API

```powershell
alembic upgrade head
uvicorn app.main:app --reload
```

Development endpoints:

- API: `http://localhost:8000`
- OpenAPI documentation: `http://localhost:8000/docs`
- Health endpoint: `http://localhost:8000/health`

### 6. Run tests

```powershell
python -m pytest -q
```

## Docker Development: All Services

Ensure `.env` uses the Docker hostnames from `.env.example`:

```env
DATABASE_URL=postgresql+psycopg://postgres:postgres@postgres:5432/vision_ai
REDIS_URL=redis://redis:6379/0
```

Build and start the complete stack:

```powershell
docker compose up --build -d
docker compose ps
```

The image installs the pinned CPU-only PyTorch and torchvision wheels from the
official PyTorch package index. This matches `MODEL_DEVICE=cpu` and avoids
shipping an unused CUDA runtime in the development/production image.

Verify the running application and infrastructure:

```powershell
curl.exe -i http://localhost:8000/health
docker compose exec postgres pg_isready -U postgres -d vision_ai
docker compose exec redis redis-cli ping
```

Run the complete test suite inside the API container:

```powershell
docker compose exec api python -m pytest -q
```

### W6D1 Reproducible Real-Inference Gate

The deterministic W6D1 regression gate covers authenticated upload and
readback, the production package-loader/scorer/preprocessing/worker path,
invalid input, unavailable artifacts, safe worker failure, terminal-job
non-reprocessing, and non-disclosing cross-owner reads. It creates only
temporary package fixtures, so generated model binaries remain outside Git:

```powershell
docker compose exec api python -m pytest -q -m w6_inference_gate
```

After provisioning the configured Week 4 package, feature bank, and cached
ResNet-18 checkpoint described in
[Before Running Real Inference](#before-running-real-inference), prove the
running API, PostgreSQL queue, production worker, and actual configured package
with one command:

Docker reads the checkpoint from the ignored repository-local Torch cache. On
Windows, provision the already-validated host checkpoint once with:

```powershell
New-Item -ItemType Directory -Force artifacts/weights/hub/checkpoints
Copy-Item "$env:USERPROFILE/.cache/torch/hub/checkpoints/resnet18-f37072fd.pth" artifacts/weights/hub/checkpoints/
```

```powershell
docker compose exec api python scripts/prove_real_inference.py
```

The deployed-stack probe creates isolated local-development users, uploads a
small PNG through the authenticated API, confirms another user receives the
same non-disclosing `404` as a missing prediction, waits for the worker, and
validates the persisted score, threshold, label, latency, package ID, and
public-safe lineage. If package members or weights are unavailable, the worker
fails closed and the probe reports `inference_failed`; inspect the worker logs
for the private local diagnostic.

View API logs:

```powershell
docker compose logs --tail=100 api
```

Stop the stack:

```powershell
docker compose down
```

To intentionally delete the local PostgreSQL development volume as well:

```powershell
docker compose down -v
```

## Image Preprocessing Contract

Every stored image passed to the future model boundary follows this deterministic pipeline:

1. Decode the actual image content with Pillow.
2. Apply EXIF orientation correction.
3. Convert the image to RGB.
4. Resize it to the configured model dimensions.
5. Convert it to a NumPy `float32` array.
6. Normalize pixel values to `[0, 1]`.
7. Convert the layout from HWC to CHW.
8. Verify shape, contiguity, and finite values.

Default output contract:

```text
shape: (3, 224, 224)
dtype: float32
layout: CHW, C-contiguous
range: [0.0, 1.0]
```

The deterministic contract prevents training-serving skew caused by different image transformations in offline and online paths.

## Week 2 Architecture Decisions

### Product boundary

VDDAI remains domain-agnostic. Platform components should be reusable across printing, ceramics, manufacturing, and other visual-inspection environments.

### Data strategy

Customer data collection must not block platform development. MVTec AD, beginning with its `tile` category, will be used for the first real anomaly-detection pipeline. Customer-specific data can later support adaptation and pilot validation.

### Security boundary

The authenticated server determines prediction ownership and opaque image
object keys. Clients cannot select another user, storage key, or filesystem
destination.

### Processing boundary

Real decoding and deterministic preprocessing preceded background-job
reliability. The current queue remains PostgreSQL-backed and now adds bounded
retries, leases, recovery, and attempt fencing without another queue service.

### Time representation

Existing database columns remain timezone-naive for compatibility. UTC timestamps are calculated explicitly with Python's timezone-aware API before the timezone information is removed for persistence. A future database migration can convert these columns to timezone-aware types.

## Known Risks and Deferred Work

- MIME type initially comes from client-provided multipart metadata.
- The configured image-storage implementation is local; multi-instance
  deployment still requires a shared object-store implementation.
- Object deletion is not yet coupled to prediction-record deletion, and no
  automated retention scheduler is implemented.
- The current credentials and secrets are development values.
- Database polling remains intentionally simple: there is no lease heartbeat,
  append-only attempt ledger, or external queue orchestrator. Work that exceeds
  its configured lease may be computed again, while attempt fencing prevents a
  stale worker from overwriting the authoritative result.
- Operational metrics, tracing, and production alerting are not yet implemented.

## Week 3 Handoff

Week 3 introduces the first real data pipeline:

- download and validate MVTec AD;
- begin with the `tile` category;
- define train, validation, and test manifests;
- add dataset-integrity checks;
- connect dataset preprocessing to the existing image contract;
- record dataset versions and preprocessing configuration;
- continue *Designing Machine Learning Systems* with VDDAI-specific decisions.

## Learning Track

*Designing Machine Learning Systems* by Chip Huyen is studied alongside implementation. Each chapter must produce at least one recorded VDDAI design decision. All chapters must be completed before Phase 3: Productize begins.

## MVTec AD Tile Dataset

Week 3 introduces the first real visual anomaly-detection dataset boundary using the `tile` category from MVTec AD.

Raw dataset files are stored locally and excluded from Git. The repository versions only:

- dataset source and acquisition metadata;
- archive checksum;
- deterministic acquisition logic;
- dataset structure and image-integrity validation;
- image-to-mask associations;
- focused integrity tests.

Validated local dataset summary:

```text
Input images: 347
Training images: 230 normal images
Test images: 117
Ground-truth masks: 84
Image size: 840 × 840
Image format: PNG
Corrupt files: 0
Unsupported files: 0
Mask association errors: 0
```

## Deterministic Dataset Manifests

VDDAI converts the validated MVTec AD `tile` dataset into explicit, reproducible train, validation, and test manifests.

The split policy preserves the official benchmark boundary:

- `train`: normal images selected from `train/good`;
- `validation`: a deterministic held-out subset of `train/good`;
- `test`: the complete official MVTec test set, including normal and defective images.

The training and validation split uses a fixed random seed and configurable validation ratio. The official test set is never mixed into model-development splits.

Each manifest record contains:

- a stable sample ID derived from the relative image path;
- the relative image path;
- the assigned split;
- binary anomaly label;
- defect class name;
- anomaly status;
- associated ground-truth mask path when available;
- original image dimensions;
- detected image format and color mode.

Generated manifests are written in both JSON and CSV formats:

```text
data/metadata/mvtec_ad_tile_manifest.generated.json
data/metadata/mvtec_ad_tile_manifest.generated.csv
```

These files are deterministic generated artifacts and are excluded from Git. The repository versions the manifest-generation implementation, dataset acquisition metadata, archive checksum, split seed, validation ratio, and dataset-version fingerprint.

Generate the manifests with:

```powershell
python -m ml.data.build_manifest
```

Current split contract:

```text
Train: 184 normal images
Validation: 46 normal images
Test: 117 official test images
Total: 347 input images
Random seed: 42
Validation ratio: 0.20
```

The dataset version is calculated as a SHA-256 fingerprint over the canonical serialized manifest records. Regenerating the same dataset with the same configuration produces the same split assignments and dataset version.

Automated tests verify:

- stable sample identifiers;
- deterministic regeneration;
- non-empty splits;
- mutual disjointness between train, validation, and test;
- absence of train/test leakage;
- correct anomaly labels;
- correct image-to-mask associations;
- rejection of invalid split configurations.

### Shared offline and online preprocessing

Dataset manifest records are resolved relative to the configured dataset root and passed through the same deterministic preprocessing service used by the inference application.

The preprocessing boundary guarantees:

- EXIF orientation correction;
- RGB conversion;
- deterministic bilinear resizing;
- NumPy `float32` output;
- normalization to `[0, 1]`;
- CHW layout;
- C-contiguous memory;
- finite-value and shape validation;
- rejection of absolute paths and dataset-root traversal.

This shared implementation reduces training-serving skew by preventing offline dataset code from silently introducing a different pixel transformation pipeline.

### Manifest dataset and batch contract

Validated manifest records are exposed through a framework-independent dataset loader.

Each dataset sample contains:

- deterministic sample and source identifiers;
- preprocessed `float32` image data in CHW layout;
- binary anomaly label;
- defect class metadata;
- a binary segmentation mask in `1 × H × W` format;
- an explicit flag indicating whether a ground-truth mask exists.

Normal samples receive an all-zero mask so that every sample has a fixed shape. Defective samples load their associated MVTec ground-truth masks.

Image and mask transformations intentionally use different interpolation policies:

- images use bilinear resizing;
- segmentation masks use nearest-neighbor resizing.

Batches use the following contract:

```text
images:    (N, 3, H, W), float32, range [0, 1]
labels:    (N,), int64
masks:     (N, 1, H, W), uint8, values {0, 1}
has_masks: (N,), bool
```

## Week 3 Architecture Decisions

### Dataset lineage

Raw MVTec AD files and generated manifests remain local and excluded from Git. Reproducibility is established through acquisition metadata, archive checksums, validation logic, split configuration, stable sample identifiers, and a canonical dataset-version fingerprint.

### Evaluation boundary

The official MVTec test set remains untouched. Only normal images from `train/good` are deterministically divided into training and validation sets. Test data never influences model development.

### Training-serving consistency

Offline dataset processing and online inference use the same deterministic image-preprocessing implementation. This reduces training-serving skew and makes pixel-level behavior independently testable.

### Segmentation-mask semantics

Ground-truth masks use nearest-neighbor resizing and explicit binary thresholding. Normal samples receive fixed-shape zero masks, allowing normal and anomalous samples to share one batch contract.

### Framework boundary

Dataset semantics are implemented with NumPy and Pillow before adopting PyTorch. The future framework adapter should convert an already validated contract rather than redefine dataset behavior.

## Week 3 Exit Criterion

Week 3 is complete when the MVTec AD `tile` category is:

- structurally validated;
- checked for corruption and unsupported files;
- associated with its anomaly masks;
- deterministically split;
- versioned;
- processed through the shared image contract;
- exposed as fixed-shape samples and batches;
- verified by an end-to-end reproducibility report;
- covered by automated tests.

## Week 4 Complete

The Week 4 image-level anomaly baseline is complete. Its exit criteria verify
the train-only normal feature bank, validation-only threshold calibration,
official-test-only final evaluation and qualitative analysis, deterministic
data loading, shared preprocessing, frozen model adapter, and reproducible
artifact lineage.

The objective is anomaly detection, not multiclass defect classification. The
baseline represents normal tile appearance from the training split and
produces image-level anomaly scores for validation and official test images.

Week 4 delivers:

- the PyTorch adapter and deterministic data loading;
- a pretrained feature-extraction baseline;
- image-level anomaly scores;
- threshold selection using validation data only;
- ROC-AUC and precision-recall evaluation;
- segmentation-aware qualitative error analysis;
- reproducible model artifacts and metrics.

PyTorch data loading uses an explicit configuration boundary for batch size,
worker count, pinned memory, `drop_last`, and random seed. Training loaders are
seeded and may shuffle; validation and test loaders preserve manifest order.
The seed is applied to Python `random`, NumPy, PyTorch, the DataLoader
generator, and worker initialization when workers are enabled. This controls
sample ordering and seeded execution, but it does not claim bitwise-stable
results for PyTorch operations that are documented as nondeterministic.

The first representation baseline uses a torchvision pretrained ResNet-18 as a
frozen feature extractor. VDDAI removes the classifier head and uses the
global-average-pooled penultimate output, producing one 512-dimensional feature
vector per image. Dataset tensors remain in the shared storage-level contract:
`(N, 3, H, W)`, `float32`, range `[0, 1]`. ImageNet mean/std normalization is
applied inside the ResNet adapter only, because it is model-specific and must
not change the shared preprocessing contract. The backbone is frozen and kept
in evaluation mode so Week 4 measures fixed pretrained representations before
any training or fine-tuning. CPU execution is supported by default; CUDA can be
selected explicitly when available but is not required.

Generate the normal-training reference feature bank with:

```powershell
python -m ml.generate_feature_bank
```

The default output directory is
`artifacts/feature_banks/mvtec_ad_tile_train_resnet18/`. It contains a
compressed NumPy archive with the row-aligned feature matrix, sample IDs,
relative source paths, split names, and dataset versions, plus JSON metadata
describing the extractor, weights, feature layer, normalization, image size,
manifest fingerprint, seed, schema version, and UTC creation time. Files are
written through temporary siblings and atomically replaced; the metadata also
records the feature archive checksum. Generated feature banks are excluded from
Git. The command uses only normal records from the training split and does not
perform anomaly scoring or threshold selection.

Generate exact Euclidean nearest-neighbor anomaly scores with:

```powershell
python -m ml.score_anomalies --k 1
```

The scorer returns the mean distance to the `k` nearest normal feature-bank
vectors, so `k=1` is ordinary nearest-neighbor distance and higher values
indicate greater anomaly likelihood. The command scores validation and test
records in manifest order and writes
`artifacts/anomaly_scores/mvtec_ad_tile_resnet18_knn/scores.json` with each
sample's metadata and complete dataset, feature-bank, extractor, and scorer
lineage. Labels are recorded for later evaluation only. This step does not
select a threshold or calculate final test metrics.

Select a normal-only validation quantile threshold with:

```powershell
python -m ml.select_threshold --quantile 0.95
```

This policy computes a linear quantile from normal validation anomaly scores
only. It is an unsupervised calibration rule, not a threshold optimized for
classification F1, ROC, precision, or recall. Official test scores and labels
never enter selection. Prediction semantics are explicit: `score > threshold`
is anomalous, while `score <= threshold` is normal. The generated threshold
artifact records validation score statistics, estimated validation
false-positive rate, quantile policy, source-score checksum, and complete
dataset, feature-bank, extractor, and scorer lineage.

Produce one complete official-test image-level evaluation run with:

```powershell
python -m ml.evaluate_baseline --threshold-quantile 0.95
```

The positive class is anomalous (`label=1`), and continuous scores are used in
their original direction with higher values meaning more anomalous. The command
requires a training-only feature-bank lineage, selects the threshold from
normal validation scores only, and evaluates official-test records once without
retuning. It stores ROC-AUC, full precision-recall curve data, non-interpolated
average precision, thresholded confusion and rate metrics, per-defect score
summaries, distribution summaries, test sample CSV, threshold metadata, and
evaluation configuration. Each run also contains `run_manifest.json`, which
records the effective seed, scorer and threshold configuration, protocol roles,
dataset and model lineage, threshold policy, and checksums for the other run
artifacts. Accuracy is included but can be misleading under class imbalance.

Each default run receives a unique timestamped directory under
`artifacts/evaluations/`. A named run fails when it already exists unless
`--existing-run-policy overwrite` is supplied explicitly. Generated evaluation
runs are excluded from Git. Unit tests do not generate plots.

Generate segmentation-aware qualitative error analysis for an evaluation run:

```powershell
python -m ml.generate_error_analysis `
  --run-dir artifacts/evaluations/<run-name>
```

The command categorizes official-test samples into TP, TN, FP, and FN review
queues; ranks high-scoring normals, low-scoring anomalies, and confident
errors; and describes available ground-truth masks using anomalous pixel count,
area ratio, and bounding box. It writes deterministic JSON and Markdown
reports under the evaluation run. Small-anomaly analysis compares false
negative rates at or below versus above the median annotated anomaly area.

This remains an image-level baseline. Ground-truth masks are used only as
post-prediction annotations for descriptive error analysis. They are not
model-generated localization, heatmaps, or pixel-level predictions. The report
must not be used to retune the Week 4 model or threshold on official-test
errors. Contact sheets, overlays, connected-component counts, and plots are not
generated by this command.

## Week 4 Architecture Decisions

### Frozen pretrained representation

The baseline uses a pretrained ResNet-18 because a frozen general-purpose
visual representation provides a simple, auditable anomaly baseline without
requiring anomalous training examples. The classifier is removed and the
512-dimensional global-average-pooled feature is used for exact nearest-neighbor
comparison against normal training features. Freezing the backbone and keeping
it in evaluation mode isolates representation quality before any fine-tuning or
task-specific training is introduced.

### Normal-only threshold calibration

The threshold is the configured quantile of normal validation scores. This
matches the available validation contract, estimates an acceptable normal
false-positive boundary, and avoids pretending that a supervised optimum can
be learned without representative validation anomalies. It is not optimized
for F1, ROC-AUC, precision, or recall.

### Official test isolation

Training records alone build the reference feature bank, and validation records
alone select the threshold. Official-test labels are opened only for the frozen
evaluation and ground-truth masks are used only for post-prediction descriptive
analysis. Test metrics and error cases must not be used to retune this Week 4
baseline; doing so would convert the official test set into calibration data.

### Separate model normalization

Canonical preprocessing remains deterministic CHW `float32` in `[0, 1]` for
both offline datasets and online serving. ImageNet channel normalization lives
inside the ResNet feature adapter because it is a model-specific input
requirement. Moving it into shared preprocessing would change the storage-level
contract and couple every future model to ResNet assumptions.

### Limitations and Week 5 handoff

This baseline emits one global image feature and one image-level score. It does
not localize anomalous pixels, exact nearest-neighbor scoring scales linearly
with feature-bank size, normal-only quantile calibration is not a supervised
operating-point optimum, and the current evidence is limited to the MVTec AD
tile category. Small `gray_stroke` and `rough` defects remain the main
qualitative failure group.

Week 5 should consume the frozen run manifest and lineage contracts when
building the production inference boundary. Any spatial or patch-level method
motivated by the error analysis should be treated as a new experiment with a
fresh validation protocol, not as an in-place retuning of the completed Week 4
result.

## Week 5 Production Inference

The versioned serving boundary is frozen in
`docs/decisions/0003-production-inference-contract.md` and executable from
`app/contracts/inference.py`. Downstream artifact loading and worker inference
must import that contract rather than redefine score, threshold, label,
lineage, lifecycle, or failure semantics.

The production flow is now:

```text
authenticated upload -> queued prediction -> worker claim
  -> deterministic CHW preprocessing -> frozen ResNet-18 features
  -> exact k-nearest normal distance -> frozen validation threshold
  -> persisted result and lineage -> authenticated read/history
```

Run the continuous worker with:

```powershell
python -m app.workers.prediction_worker
```

The worker runs continuously and polls the database-backed queue at the
configured interval. Docker Compose starts this worker only after the API has
completed migrations and passed its health check.

`MODEL_REGISTRY_PATH` identifies the local registry and `MODEL_ARTIFACT_ROOT`
constrains its repository-relative artifact paths. The worker reads exactly the
version selected by the registry's production pointer; it never scans for the
newest directory or falls back to legacy paths. The selected package still
contains the run's `run_manifest.json` and referenced `threshold.json`, plus
the bank's `metadata.json` and referenced `features.npz`. See ADR 0004 for the
package validation contract and ADR 0008 for registry-selected serving.

`GET /health/model` reports the immutable selected version and package ID. It
does not expose registry or artifact paths. A missing or invalid production
selection returns `503` and inference fails closed until a human-approved
candidate is promoted.

`ModelPackageLoader` validates both artifact checksums, package-relative paths,
supported schemas, training/validation split policy, row-aligned archive
lineage, MVTec AD `tile` identity, 224x224 preprocessing, frozen ResNet-18
contract, 512-dimensional features, valid `k`, finite threshold, strict
comparison semantics, and run/threshold/bank compatibility before returning a
frozen ready-to-score package. Missing, malformed, corrupt, test-derived, or
incompatible inputs raise a specific package error and return no partial
package.

The first claimed job loads the package lazily. A process-local one-entry cache
then reuses that exact package for every later job in the worker process;
requests never reload it. Serving never substitutes mock output, a default
threshold, random weights, regenerated artifacts, or downloaded weights.

For each claimed row, the worker resolves its opaque server-controlled object
key through the configured image-storage backend, reads the stored bytes,
applies the shared EXIF/RGB/224x224 bilinear preprocessing contract,
extracts one frozen ResNet-18 vector, computes the exact configured nearest-
neighbor distance, and applies the package threshold. The former random mock
and tabular model services are not part of the application or worker path.

`latency_ms` uses `time.perf_counter()` and measures from immediately before
stored-image decoding through preprocessing, feature extraction, scoring, and
the final label decision. Queue wait time, package initialization, and database
commits are excluded. The worker clears stale result/error fields when an
attempt starts and writes the completed result atomically. Retryable failures
return the job to an internal waiting substate; terminal or exhausted failures
clear result data and persist a clean failed state. Detailed diagnostics remain
internal, while the authenticated API exposes only `inference_failed` for a
terminal failure.

The worker loads pretrained weights only from the local torch cache. Provision
the exact `IMAGENET1K_V1` ResNet-18 checkpoint and the configured generated
artifacts outside Git before starting a production worker. Generated feature
banks, thresholds, evaluation runs, weights, datasets, and secrets remain
excluded from version control.

Completed prediction rows persist the image-level `normal`/`anomalous` label,
finite raw anomaly score, finite exact threshold, deterministic package ID,
complete versioned package lineage, latency in milliseconds, and created,
processing-started, and completed timestamps. The explicit columns hold values
used for display, filtering, and lifecycle checks. The JSON lineage is one
immutable `vddai.inference_package.v1` audit snapshot containing package and
contract schemas, ResNet-18 identity and weights, feature-bank checksum,
dataset/category/version and manifest fingerprint, preprocessing schema,
Euclidean scorer configuration and `k`, and threshold policy/checksum. It does
not contain absolute local paths, model weights, or feature-bank content.

Lifecycle nullability is strict: queued rows contain no processing timestamp or
result; processing rows contain only the start timestamp; completed rows require
the full result, lineage, and all three timestamps; failed rows contain the
start/terminal timestamps and safe failure code but no stale result. Timestamps
are normalized to timezone-naive UTC for compatibility. The legacy
`confidence` field is deprecated and always null; anomaly distance is exposed
only as `anomaly_score`.

`GET /predictions/{id}` returns a single authorized result and safe image
metadata without the object key or an internal backend location.
`GET /predictions?limit=50&offset=0` returns newest-first history scoped to the
current owner; administrators retain the existing cross-owner read privilege.
PostgreSQL workers use row locking with `SKIP LOCKED` so concurrent workers do
not claim the same eligible row.

### Prediction Reliability and Recovery

Every accepted `POST /predictions` creates a distinct prediction job. The API
does not deduplicate equal image bytes or filenames and does not define an
idempotency-key header in v0.1.0. Idempotency applies to execution of one
persisted job: computation may occur more than once after a lease expires, but
only the current attempt token may persist an authoritative result or failure.

The public lifecycle remains `queued -> processing -> completed|failed`, with
`needs_review` retaining its existing successful-result semantics. Retry wait
is internal: clients continue to see `processing`, no result fields, and no
failure code. The database stores `attempt_count`, `lease_expires_at`, and
`next_attempt_at`; these fields and internal diagnostics are not public API
members.

The worker performs these transactionally separate steps:

1. recover at most one expired or legacy lease-less active row;
2. lock the oldest queued or due-retry row with `FOR UPDATE SKIP LOCKED`;
3. increment its attempt token, assign a lease, and commit the claim;
4. read storage and run inference without holding a database transaction; and
5. relock the row and persist only when status and attempt token are current.

An interruption before claim commit leaves the job eligible. An interruption
after commit, during inference, or before terminal persistence leaves a leased
`processing` job that another worker recovers after expiry. An old worker may
finish computing, but its stale token cannot overwrite a replacement attempt.
Terminal rows are never selected again.

Generic storage-backend read failures, result-commit failures, and expired
leases are retried up to `WORKER_MAX_ATTEMPTS`. Missing stored objects, invalid
object keys, preprocessing errors, promoted-model resolution or package
failures, post-claim lifecycle validation errors, and unknown execution errors
are terminal. Retry exhaustion is terminal. The stable public failure code
remains `inference_failed`; inspect worker logs and the internal database
diagnostic for operator detail.

Apply migrations before starting the new worker code:

```powershell
alembic upgrade head
```

Revision `20260820_03` adds non-null `attempt_count` with default `0` plus
nullable `lease_expires_at` and `next_attempt_at`, preserving existing rows.
Legacy `processing` rows without a lease are treated as stale and enter bounded
recovery. Stop old workers before applying the migration and do not run old and
new worker versions concurrently; old workers do not participate in attempt
fencing.

For a code rollback, first stop every worker and confirm no `processing` row
depends on retry or lease metadata. Then downgrade only this revision and
deploy the matching older worker:

```powershell
alembic downgrade 20260803_02
```

The downgrade preserves prediction rows and prior result fields but removes
the three W7D2 metadata columns. Removing them while retry-waiting or leased
work exists discards its recovery metadata. See
[ADR 0010](docs/decisions/0010-database-backed-prediction-reliability.md) for
the durable state-machine, failure-classification, and compatibility decision.

### PostgreSQL 16 migration verification

The complete Week 5 migration chain was verified on 3 August 2026 against an
isolated PostgreSQL 16.14 database containing a pre-Alembic `predictions` table
and a legacy row with `threshold=0.9` and `model_version=legacy-v1`.

`python -m alembic upgrade head` applied revisions `20260801_01` and
`20260803_02`. The upgraded schema made `threshold` and `model_version`
nullable without defaults, added nullable `anomaly_score`, `model_lineage`, and
`processing_started_at` columns, and preserved the legacy values.

`python -m alembic downgrade base` reversed both revisions. The three new
columns were removed, the non-null `0.75` and `mock-v0` defaults were restored,
and the legacy values remained unchanged. The disposable verification database
was removed after the check.

On 21 August 2026, W7D2 QA also verified revision `20260820_03` on a disposable
PostgreSQL 16 database. A legacy `processing` row retained its status,
threshold, package ID, and internal diagnostic; upgrade initialized
`attempt_count=0` with null lease/retry timestamps. Targeted downgrade removed
only the three W7D2 columns, re-upgrade succeeded, and the disposable database
was removed.

Week 5 exits when an authenticated upload can be queued, processed by the
frozen Week 4 model package, persisted with the exact score/threshold/label and
lineage, and read only by an authorized user; corrupt input must end in a safe
failed state. The executable evidence is the inference-contract, package-loader,
inference-service, worker/API integration, ownership, orphan-cleanup, rollback,
and Alembic upgrade/downgrade tests in `app/tests`.

## Week 6 Experiment Tracking

W6D2 records the frozen Week 4 baseline in a queryable local SQLite ledger. It
does not rerun or retune the official-test evaluation. The import validates the
existing run manifest, frozen train/validation/test protocol, dataset and
feature-extractor lineage, feature bank, score artifact, evaluation members,
and every recorded SHA-256 checksum before creating a completed experiment.

Commit the tracking implementation first so the run receives an exact, clean
Git revision. Then track the existing baseline with an immutable run ID:

```powershell
python -m ml.track_baseline_experiment `
  --run-id week4-baseline-q95-20260729
```

The default ledger is
`artifacts/experiments/experiments.sqlite3`. It is generated and excluded from
Git together with feature banks, scores, thresholds, evaluations, model
weights, and datasets. The experiment records the ResNet-18 extractor and
weights, feature layer and dimension, scorer and `k`, threshold policy,
quantile and value, random seed, dataset version and manifest fingerprint,
full code revision, headline evaluation metrics, artifact locations and
checksums, schema/code versions, timestamps, and terminal status.

Query one run:

```powershell
python -m ml.query_experiments --run-id week4-baseline-q95-20260729
```

Query completed runs or filter by dataset version:

```powershell
python -m ml.query_experiments --status completed
python -m ml.query_experiments --dataset-version <dataset-version>
```

Run IDs are immutable. Completed and failed runs are terminal, and a duplicate
ID is rejected rather than overwritten. Experiment tracking is evidence only:
it does not register a model candidate, promote a package, change serving
configuration, or bypass the human approval required for production promotion.
See
`docs/decisions/0006-queryable-experiment-ledger.md` for the durable boundary.

## Roadmap

The 11-week project moves through:

1. foundation and product definition;
2. real image-data engineering;
3. anomaly-detection baselines;
4. production inference;
5. experiment tracking and model registry;
6. human review and feedback;
7. testing, CI/CD, and observability;
8. deployment and pilot packaging;
9. portfolio case study and customer applications.

## License

No public license has been selected yet. All rights are reserved unless a license is added to the repository.
