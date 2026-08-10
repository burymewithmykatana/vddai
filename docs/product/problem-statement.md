# Problem Statement

- Status: Draft hypothesis; customer validation required
- Last reviewed: 2026-08-10

## Problem

Small and medium manufacturers often depend on manual visual inspection that is
variable, difficult to audit, and expensive to scale. Before investing in a
custom machine-vision deployment, they need evidence that one constrained
inspection point is visually learnable, operationally measurable, and capable
of producing useful decisions under controlled image-capture conditions.

## Primary Users

- quality-control operators who inspect products and review uncertain cases;
- production or quality engineers who define acceptance criteria and investigate
  failures;
- operational sponsors who decide whether a pilot justifies production
  investment.

## Jobs to Be Done

- determine whether available images and labels can support a credible pilot;
- detect or rank visually abnormal products consistently;
- route uncertain or high-risk cases to human review;
- trace every decision to its input, model package, threshold, and dataset
  lineage;
- quantify technical limitations and operational value before deployment.

## Impact Hypotheses

VDDAI may reduce inconsistent inspection, missed defects, unnecessary rejection,
manual review effort, and the cost of evaluating a custom vision use case.
These are hypotheses until customer discovery and a customer-domain pilot
provide evidence.

## Non-Goals

- a universal model for arbitrary products;
- immediate autonomous rejection of physical products;
- replacement of customer quality experts;
- regulatory or safety certification;
- production ROI claims based only on MVTec benchmark results.

## Evidence Needed

- repeated customer interviews describing the same costly inspection problem;
- representative normal and defective images from a controlled inspection point;
- stable acceptance criteria from a domain expert;
- baseline false-negative and false-positive consequences;
- measured manual effort, defect cost, rework, or throughput constraints;
- an agreed pilot decision rule and success measures.

Record evidence in [`customer-discovery.md`](customer-discovery.md) and define
the decision measures in [`success-metrics.md`](success-metrics.md).
