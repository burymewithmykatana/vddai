# VDDAI Backend

Production-oriented backend for a domain-agnostic visual inspection and anomaly-detection platform.

VDDAI is being developed as a contract-ready pilot platform rather than a detector tied to one product category. Engineering currently uses controlled test images; MVTec AD will provide baseline anomaly-detection data before customer-specific datasets are introduced.

## Current Status

Week 3 is complete. VDDAI now provides a validated and reproducible visual-anomaly dataset pipeline in addition to the production-oriented backend.

- FastAPI application and health endpoint
- PostgreSQL persistence with SQLAlchemy
- Redis infrastructure
- JWT authentication and active-user validation
- User-owned prediction records
- Authenticated multipart image ingestion
- Server-controlled UUID storage paths
- File-size and media-type validation
- Image dimension and format metadata
- Prediction lifecycle states
- Deterministic image preprocessing
- EXIF orientation correction
- RGB conversion
- Fixed CHW model input
- `float32` normalization to `[0, 1]`
- Automated API and service tests
- Reproducible local and Docker execution
- Validated MVTec AD `tile` dataset ingestion
- Deterministic train, validation, and test manifests
- Stable dataset-version fingerprinting
- Shared offline and online preprocessing
- Ground-truth anomaly-mask processing
- Framework-independent dataset and batch contracts
- End-to-end dataset reproducibility reporting

Current verification result:

```text
77 passed, 0 warnings
```

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
artifacts/               # Generated model artifacts and metrics
uploads/                 # Local development image storage
Dockerfile               # API container definition
docker-compose.yaml      # API, PostgreSQL, and Redis stack
requirements.txt         # Pinned Python dependencies
.env.example             # Development configuration template
```

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

CONFIDENCE_THRESHOLD=0.75
MAX_IMAGE_SIZE_MB=5
```

Replace `JWT_SECRET_KEY` before running the application outside isolated local development. Never commit the real `.env` file.

## Local Development

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

## Docker Development

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

The authenticated server determines prediction ownership and image storage paths. Clients cannot select another user or provide arbitrary filesystem destinations.

### Processing boundary

Real decoding and deterministic preprocessing are implemented before expanding background-job infrastructure. Queue complexity will be added only after the image-to-model boundary is measurable and testable.

### Time representation

Existing database columns remain timezone-naive for compatibility. UTC timestamps are calculated explicitly with Python's timezone-aware API before the timezone information is removed for persistence. A future database migration can convert these columns to timezone-aware types.

## Known Risks and Deferred Work

- MIME type initially comes from client-provided multipart metadata.
- Image storage is local and is not suitable for multi-instance deployment.
- File deletion is not yet coupled to prediction-record deletion.
- Schema evolution needs a formal Alembic migration workflow.
- The current credentials and secrets are development values.
- The ML service is not yet connected to a real anomaly-detection model.
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

## Week 4 Handoff

Week 4 introduces the first real anomaly-detection baseline.

The initial objective is not multiclass defect classification. The model must learn a representation of normal tile appearance from the training split and produce anomaly scores for validation and official test images.

Week 4 will establish:

- the PyTorch adapter and deterministic data loading;
- a pretrained feature-extraction baseline;
- image-level anomaly scores;
- threshold selection using validation data only;
- ROC-AUC and precision-recall evaluation;
- segmentation-aware qualitative error analysis;
- reproducible model artifacts and metrics.

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
