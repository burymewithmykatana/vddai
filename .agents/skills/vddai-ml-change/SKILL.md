---
name: vddai-ml-change
description: Implement or plan VDDAI ML, data, and artifact changes while preserving split isolation, preprocessing consistency, lineage, schema compatibility, and production serving contracts. Use for changes to dataset manifests, preprocessing, feature extraction, feature banks, anomaly scoring, threshold selection, evaluation, error analysis, experiment tracking, model registry or package formats, and serving-related ML artifacts. Do not use for unrelated API-only or generic repository changes.
---

# Change VDDAI ML Safely

Preserve reproducibility, leakage boundaries, artifact compatibility, and production lineage while planning or implementing an ML change.

## Establish context

1. Read the task, acceptance criteria, and constraints.
2. Read the root `AGENTS.md` and `ml/AGENTS.md`. Read another nested `AGENTS.md` when the change crosses into its scope.
3. Inspect the relevant code, tests, schemas, configuration, and architecture decision records before editing.
4. Identify the active pipeline. Do not treat `ml/preprocessing.py` or `ml/train_baseline.py` as the active production path unless the task explicitly concerns those legacy modules.
5. Determine whether the task changes a contract or only its implementation.

## Complete the ML preflight

Evaluate every item below before implementation:

- dataset manifest or sample identity;
- train, validation, and test split policy;
- preprocessing and image normalization;
- feature extractor identity and weights;
- feature dimension or tensor shape;
- feature-bank construction and serialization;
- anomaly scorer, nearest-neighbor behavior, or `k`;
- threshold-selection policy;
- evaluation protocol and reported metrics;
- artifact schema, version, checksum, and compatibility rules;
- model-package contents and lineage;
- experiment tracking, registry, and promotion metadata;
- online inference inputs, outputs, and fail-closed loading.

For every affected item, record:

1. the current code or schema version and source of truth;
2. the intended compatibility behavior;
3. which existing artifacts become invalid;
4. how invalidated artifacts will be regenerated;
5. the tests required to prove the contract;
6. leakage implications;
7. offline-evaluation and online-inference consistency;
8. lineage, registration, and promotion implications.

If compatibility cannot be established safely, fail closed and require explicit regeneration or version migration. Never silently reinterpret an existing artifact.

## Protect dataset integrity

- Preserve deterministic sample identity and split assignment.
- Keep training data for fitting, validation data for model or threshold selection, and test data for final unbiased evaluation.
- Never use test labels, test metrics, test-derived thresholds, or test-driven iteration to select model behavior.
- Check indirect leakage through duplicates, derived samples, shared source groups, cached features, preprocessing statistics, or reused artifacts.
- Make split or manifest changes explicit, versioned, and covered by deterministic tests.

## Preserve active pipeline contracts

- Keep preprocessing identical between artifact creation, offline evaluation, and production inference.
- Treat extractor identity, weights, preprocessing, feature dimension, scorer configuration, and threshold policy as compatibility-critical metadata.
- Version intentional schema or behavioral contract changes. Maintain backward compatibility only when it is explicit and testable.
- Reject malformed, incomplete, mismatched, or unverifiable packages before inference.
- Preserve model and experiment lineage through package creation, loading, inference persistence, and observability.
- Keep model registration separate from production promotion. Promotion remains an explicit human-controlled gate.

## Implement the smallest coherent change

1. Change only the components required by the task and the tests or documentation needed to keep their contracts truthful.
2. Prefer deterministic behavior and explicit metadata over inference from filenames or ambient state.
3. Add focused tests for the changed contract, including invalid inputs and incompatible artifacts.
4. Update documentation and configuration examples when operator-visible behavior changes.
5. Do not commit generated datasets, feature banks, model packages, experiment stores, credentials, or other runtime artifacts.

## Verify the change

Run the narrowest relevant tests during development, then run the repository verification gate from the repository root:

```powershell
.\scripts\verify.ps1
```

Use the optional Docker configuration check when the change affects service wiring or container behavior:

```powershell
.\scripts\verify.ps1 -IncludeDockerConfig
```

Record exact commands and outcomes. Do not claim unrun checks. If a check cannot run, explain why and identify the remaining risk.

Before completion, inspect the full local diff and status. Confirm that artifacts remain untracked and uncommitted, no secrets were added, and no promotion action occurred.

## Report completion

Report:

1. the completed preflight and affected contracts;
2. changed files and behavior;
3. focused and full verification results;
4. invalidated artifacts and regeneration steps;
5. compatibility and lineage effects;
6. documentation changes;
7. residual risks and required human gates.

Do not register or promote a model, commit, push, merge, or mutate production state unless the user separately and explicitly authorizes that action.
