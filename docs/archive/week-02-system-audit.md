# Week 2 System Audit

- Status: Historical
- Snapshot: Week 2

> This document records an earlier implementation state. Its mock-inference,
> worker, product, metrics, and command statements are not current requirements.
> Use the current documentation index, accepted ADRs, code, and tests instead.

## Worker Architecture

Current implementation:

- The API inserts a queued prediction into PostgreSQL.
- The worker queries the oldest queued prediction.
- The worker processes exactly one job per execution.
- The mock model simulates one second of inference.
- Results and failures are persisted in the prediction row.
- Redis is running but is not currently used by the worker.
- Celery, RQ, Dramatiq, or another queue system is not configured.

## Secure Image Ingestion

Current implementation:

- Prediction creation requires a valid bearer token.
- The prediction owner is derived from the JWT subject.
- Clients cannot provide arbitrary user IDs.
- Clients upload image bytes through multipart form data.
- Server-generated UUID filenames prevent collisions and path traversal.
- JPEG, PNG, and WebP MIME types are accepted.
- Empty and oversized uploads are rejected.
- Stored files are removed when database persistence fails.
- Ordinary users cannot read another user's prediction.
- Administrators can read predictions belonging to other users.

Remaining limitations:

- MIME type is still supplied by the client.
- Image bytes are not yet decoded or structurally validated.
- Files are stored on the local filesystem.
- There is no object-storage abstraction.
- Uploaded files are not deleted when prediction records are deleted.

## Worker Risks

1. Two workers can select the same queued prediction concurrently.
2. No atomic job-claiming or row locking exists.
3. A worker crash after setting `processing` leaves the job stuck.
4. There is no retry policy.
5. There is no timeout policy.
6. There is no continuously running worker loop.
7. Redis exists in Docker Compose but is not used.
8. The worker processes only one job per invocation.
9. Random mock inference makes tests nondeterministic.
10. `datetime.utcnow()` creates naive timestamps.
11. Image files are now uploaded through an authenticated multipart endpoint,
    but validation currently trusts the declared MIME type and does not yet
    decode the file to verify that it contains a valid image.
12. Prediction creation and retrieval are protected by JWT authentication.
    Ordinary users can access only their own predictions, while administrators
    can retrieve predictions belonging to other users.

## Product Framing

### User

A manufacturing quality-control operator or production engineer.

### Input

An image of a manufactured component or surface.

### Output

- Predicted defect class
- Confidence score
- Review requirement
- Model version
- Inference latency

### Prediction Type

Multi-class image classification for the initial portfolio version.

### Initial Classes

- normal
- scratch
- crack
- stain
- shape_defect

These are provisional mock classes and must later be aligned with the selected dataset.

### Product Objective

Reduce the amount of manual inspection required while routing uncertain
predictions to human review.

### Offline Metrics

- Macro F1
- Per-class precision and recall
- Confusion matrix
- False-negative rate for defects
- Calibration quality

### System Metrics

- Prediction latency
- Queue waiting time
- Failure rate
- Throughput
- Percentage sent to human review

### Constraints

- False negatives are more expensive than false positives.
- Predictions must remain traceable to a model version.
- Low-confidence results must not be treated as reliable automated decisions.
- The system must preserve prediction history for evaluation and auditing.

## Commercial Direction

VDDAI will continue as a visual defect and anomaly-detection system, but the
commercial product will be a reusable customer-pilot platform rather than a
single ceramic classifier.

Public datasets will be used to build and verify the platform. Customer data
will be used to adapt and evaluate each specific inspection project.

The first commercial objective is to secure a paid feasibility pilot rather
than sell a universal finished inspection model.

## Current Product Risks

1. No discovery interviews have yet validated the customer problem.
2. No first target market has been selected.
3. No customer dataset is currently available.
4. Benchmark performance may not transfer to customer images.
5. Image acquisition conditions may dominate model performance.
6. The current worker is a database-polling skeleton, not a production queue.
7. The real image model has not yet been integrated.
8. Multi-tenancy and customer data isolation are not implemented.
9. Production ROI has not yet been measured.
10. The project must avoid overbuilding infrastructure before customer discovery.


## Prediction Lifecycle Verification

The asynchronous prediction workflow is covered by 11 passing tests.

Verified behavior:

- prediction jobs are created with HTTP 202
- jobs begin with queued status
- jobs are persisted in the database
- nonexistent users are rejected
- invalid payloads are rejected
- prediction jobs can be retrieved
- missing jobs return HTTP 404
- workers complete queued jobs
- inference results are persisted
- inference failures are persisted
- empty queues are handled safely

Model inference is replaced with deterministic test doubles during worker
tests. This separates worker orchestration tests from model-quality tests.

Command:

```bash
pytest -v
```

Historical result: `11 passed`.
