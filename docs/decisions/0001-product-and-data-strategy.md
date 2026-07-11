# ADR 0001 — Product and Data Strategy

- Status: Accepted
- Date: 2026-07-11

## Context

VDDAI was initially framed as a visual defect-detection backend. A
ceramic-specific product was considered because of direct workshop access.

However, collecting and labeling enough ceramic defect images would delay
production and MLOps development. A ceramic-only product would also restrict
the available market before customer demand had been validated.

## Decision

VDDAI will be developed as a configurable visual-inspection pilot platform.

Public industrial datasets will be used to develop and evaluate the initial
ML and MLOps infrastructure. MVTec AD may be used as engineering data, but
benchmark results will not be represented as customer validation.

Each commercial pilot will target one customer-specific inspection point and
use customer-supplied or deliberately collected data.

Ceramic workshop images may be used later as a small domain-transfer case
study, but ceramic data collection will not block platform development.

## Consequences

### Positive

- Production engineering can continue immediately.
- The repository can demonstrate a complete MLOps lifecycle.
- The product can support multiple potential industries.
- Customer discovery can occur alongside development.
- A paid feasibility pilot becomes a realistic first offer.

### Negative

- The product must support configuration and dataset separation.
- Benchmark success will not prove customer-domain performance.
- Customer acquisition and data access become essential.
- Product scope must be tightly controlled to prevent becoming a generic
  no-code ML platform.