# Success Metrics

- Status: Draft framework; targets must be agreed before a customer evaluation
- Last reviewed: 2026-08-10

## Measurement Principles

- Declare pilot targets and promotion criteria before consulting final test
  outcomes.
- Separate technical model quality from operational and commercial value.
- Report false negatives and false positives in the customer's decision context.
- Preserve dataset, threshold, model-package, and code lineage for every result.
- Treat public benchmark metrics as engineering evidence, not customer success.

## Technical Measures

| Measure | Purpose | Target source |
|---|---|---|
| ROC-AUC and average precision | Evaluate continuous ranking on the frozen test set | Predeclared pilot protocol |
| False-negative rate | Quantify missed-defect risk at the frozen threshold | Customer risk tolerance |
| False-positive rate | Estimate unnecessary review or rejection workload | Operational capacity |
| Precision and recall | Explain thresholded decision quality | Predeclared pilot protocol |
| Failure rate | Measure jobs that do not reach a valid terminal result | Service-level objective |
| Inference and queue latency | Determine whether the workflow fits operations | Inspection-cycle requirement |

## Operational Measures

- percentage of inspections requiring human review;
- operator time per reviewed case;
- throughput under representative image volume;
- disagreement rate between domain experts;
- data-quality and capture failures;
- ability to reproduce a decision from persisted lineage.

## Commercial Measures

- cost of current manual inspection;
- cost and frequency of missed defects or rework;
- cost of false rejection or unnecessary review;
- expected implementation and operating cost;
- credible time to value and next-phase scope;
- named sponsor willingness to fund or authorize production work.

## Pilot Decision Record

Before a pilot begins, record the selected measures, numeric targets, dataset
boundary, evaluation protocol, responsible approver, and go/no-go rule. Do not
invent universal thresholds in this repository; customer risk and workflow
constraints determine them.

The offer and decision context are defined in
[`pilot-offer.md`](pilot-offer.md) and
[`problem-statement.md`](problem-statement.md).
