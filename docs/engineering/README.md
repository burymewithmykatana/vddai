# Engineering Documentation

This section explains current cross-component engineering behavior that is too
broad for one module but does not itself create a new architecture decision.

- [`data-lineage.md`](data-lineage.md): dataset, preprocessing, feature,
  artifact, evaluation, and production-serving lineage.
- [`agent-workflow.md`](agent-workflow.md): human-controlled role handoffs,
  evidence freshness, remediation loops, process-learning proposals, and
  merge-gate rules.
- [`repository-intelligence.md`](repository-intelligence.md): optional local
  Graphify structural discovery, freshness validation, purpose-specific
  authority, and direct-source fallback.
- [`production-readiness.md`](production-readiness.md): W7D4 production gate,
  required evidence, release conditions, and owner-tagged risk register.

Keep implementation-specific commands in the root README or scripts. Record a
new ADR when an engineering change alters a durable compatibility boundary.
