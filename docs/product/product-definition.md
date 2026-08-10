# VDDAI Product Definition

- Status: Current
- Last reviewed: 2026-08-10

## Product

VDDAI is a configurable visual-inspection platform for small and medium
manufacturers.

It provides the infrastructure required to evaluate and deploy a
customer-specific visual quality-control workflow:

- image ingestion
- asynchronous inference
- anomaly detection
- prediction history
- human review and correction
- dataset feedback
- model versioning
- experiment tracking
- deployment
- production monitoring

VDDAI is not a universal defect-detection model. Each customer pilot targets
one constrained inspection point, product family, camera setup and quality
decision.

## Problem

Many smaller manufacturers still depend on manual visual inspection. Their
inspection process may be inconsistent, poorly documented and difficult to
scale.

Developing a custom machine-vision system is risky because the manufacturer
does not initially know:

- whether its defects are visually detectable
- whether its existing images are usable
- how much data is required
- which model family is appropriate
- whether model performance can justify deployment
- how the model will be integrated and monitored

## Value Proposition

VDDAI reduces the uncertainty and engineering cost of evaluating a visual
inspection use case.

A customer can begin with a limited feasibility pilot before investing in
production-line hardware or a complete deployment.

## Initial Product Boundary

The initial version supports:

- one organization
- one inspection project
- one constrained product or surface
- uploaded or batch-imported images
- binary normal/anomalous decisions
- anomaly scores
- human review
- inspection history
- model and dataset traceability
- cloud deployment
- documented on-premise deployment architecture

The initial version does not support:

- safety-critical automated rejection
- arbitrary products using one global model
- real-time PLC integration
- multi-camera production lines
- regulatory certification
- automatic physical sorting
