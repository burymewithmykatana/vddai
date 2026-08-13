# Architecture Decision Records

ADRs are durable architecture decisions. Accepted ADRs are authoritative unless
their status or an amendment explicitly says otherwise.

| ADR | Status | Decision |
|---|---|---|
| [`0001`](0001-product-and-data-strategy.md) | Accepted | Product and data strategy |
| [`0002`](0002-anomaly-baseline-and-pytorch-data-contract.md) | Accepted; amended | Anomaly baseline and PyTorch data contract |
| [`0003`](0003-production-inference-contract.md) | Accepted | Production inference contract v1 |
| [`0004`](0004-production-model-package-loader.md) | Accepted | Production model-package loader |
| [`0005`](0005-inference-result-persistence.md) | Accepted | Auditable inference-result persistence |
| [`0006`](0006-queryable-experiment-ledger.md) | Accepted | Queryable local experiment ledger |

Create the next zero-padded number for a new decision. Preserve historical
context, record consequences, and mark replaced decisions as superseded rather
than deleting them.
