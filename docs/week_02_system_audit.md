## Worker Architecture

Current implementation:

- The API inserts a queued prediction into PostgreSQL.
- The worker queries the oldest queued prediction.
- The worker processes exactly one job per execution.
- The mock model simulates one second of inference.
- Results and failures are persisted in the prediction row.
- Redis is running but is not currently used by the worker.
- Celery, RQ, Dramatiq, or another queue system is not configured.

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
11. The API accepts an arbitrary client-provided file path.
12. The create and read endpoints do not appear protected by JWT.

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