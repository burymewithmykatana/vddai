# Architecture Decision Records

ADRs are durable architecture decisions. Accepted ADRs are authoritative unless
their status or an amendment explicitly says otherwise.

| ADR | Status | Decision |
|---|---|---|
| [`0001`](0001-product-and-data-strategy.md) | Accepted | Product and data strategy |
| [`0002`](0002-anomaly-baseline-and-pytorch-data-contract.md) | Accepted; amended | Anomaly baseline and PyTorch data contract |
| [`0003`](0003-production-inference-contract.md) | Accepted; amended | Production inference contract v1 |
| [`0004`](0004-production-model-package-loader.md) | Accepted; amended | Production model-package loader |
| [`0005`](0005-inference-result-persistence.md) | Accepted; amended | Auditable inference-result persistence |
| [`0006`](0006-queryable-experiment-ledger.md) | Accepted | Queryable local experiment ledger |
| [`0007`](0007-controlled-model-registry.md) | Accepted | Controlled local model registry |
| [`0008`](0008-registry-selected-production-package.md) | Accepted | Registry-selected production package |
| [`0009`](0009-durable-image-storage-boundary.md) | Accepted | Durable prediction-image storage boundary |

Create the next zero-padded number for a new decision. Preserve historical
context, record consequences, and mark replaced decisions as superseded rather
than deleting them.
