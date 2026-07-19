# VDDAI Backend

Production-oriented backend for a domain-agnostic visual inspection and anomaly-detection platform.

VDDAI is being developed as a contract-ready pilot platform rather than a detector tied to one product category. Engineering currently uses controlled test images; MVTec AD will provide baseline anomaly-detection data before customer-specific datasets are introduced.

## Current Status

Week 2 is complete. The backend currently provides:

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

Current verification result:

```text
44 passed, 0 warnings
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