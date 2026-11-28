# W9D3 input and model-quality monitoring re-review

## 1. Reviewed subject

Review `W9D3-REV-2026-11-27-002`, 27 November 2026. Independent re-review of
`codex/w9d3-quality-monitoring` in the W9D3 worktree. The approved base and
`HEAD` are `bd7feaff15038c345cf1a5a324d83aca4c53e3cf`. The merge base with
`origin/master` is `1b9f6160883361bdb99298b256815197ccab8eba`. The task-relative
committed and staged ranges are empty. Seven modified and four untracked
Python files form the reviewed subject. The review records are separate
audit evidence.

| Reviewed file | SHA-256 |
| --- | --- |
| `app/api/routes/prediction.py` | `5d2064f09e9e3e02f025f7a6c7cc55c998f2f60d0cb98d5aacd6966873185f20` |
| `app/core/config.py` | `f94755fbf1ca45317a60068d2562f66a3064049a9fc6f785a5f4917f1250fae1` |
| `app/services/anomaly_inference_service.py` | `0277e4735df375ce5bf4219a979c392a715d44eb93829e71479de7261eebc068` |
| `app/services/image_preprocessing_service.py` | `512eda8158d44cfb83b1cd27253c87f8b6b1c6658ad7eff7556e05bea34e5cf8` |
| `app/services/metrics_service.py` | `bd077f92554a9ff1c0602995a0e9471aa42012c87084bf6376e5c461c5a5261f` |
| `app/services/quality_monitor.py` (untracked) | `e1af34e7ceb9dd705d003e6b4b43ceaa66d57d6b5bb8903e487cebefecac9688` |
| `app/tests/test_prediction_api.py` | `8425d8e3314ffd2c89daa46880d8ca2624ad2abd6bf867d4885115c2d14244ae` |
| `app/tests/test_quality_monitor.py` (untracked) | `7b6877a0f872e2cac5f272145065fee2d07dff97aa3c2c660b5cc654924b3a09` |
| `app/workers/prediction_worker.py` | `79e846246cecd0fcd4f0f481f8fc73fc6ffd7a2cbcec230ad620210fe8c22bdd` |
| `ml/build_quality_reference.py` (untracked) | `07c41844a05c36c7b12e0a7735ee7f7ef9802f1a26ebba65b793358b8b7b5104` |
| `scripts/report_quality_shift.py` (untracked) | `49d1766d89de9a416c711b93e29a30c8ccf4d49c76d7d204ed1c14292d709a4a` |

## 2. Contract and selected findings

The approved [W9D3 task](https://app.notion.com/p/3ac0ab50ef6781e8badced236afe36cb)
requires aggregate monitoring of validated image formats, dimensions, pixel
signals, scores, and package identity. The approved design uses one bounded
rolling hour and at least 30 matched normal-validation and current
observations. The baseline and comparisons retain the frozen package,
manifest, and preprocessing identities. The local operator report reads
one captured private scrape. Durable aggregate retention belongs to W9D4.

The human selected `VDDAI-REV-001` and `VDDAI-REV-002` from the
[original review](2026-11-27-w9d3-quality-monitoring.md), preserved at
SHA-256 `846d14360c13130ed30759b7afc1afdaf439be3d97bfc4a8b16d8d078ba9d882`.
Three reviewed files changed for this remediation and eight match R1.
The [repository rules](../../AGENTS.md), [application rules](../../app/AGENTS.md),
[ML instructions](../../ml/AGENTS.md), and
[agent workflow](../engineering/agent-workflow.md) govern this review.
The [frozen inference](../decisions/0003-production-inference-contract.md)
and [package loader](../decisions/0004-production-model-package-loader.md)
contracts remain applicable.

## 3. Verdict

**PASS.** Both prior findings are verified resolved. Independent QA is
eligible on the exact implementation range above.

## 4. Finding status

| ID | Severity | Status |
| --- | --- | --- |
| `VDDAI-REV-001` A matching fingerprint can pass with overlapping splits | `HIGH` | `VERIFIED RESOLVED` |
| `VDDAI-REV-002` Decoded source mode can disagree with matched lineage | `MEDIUM` | `VERIFIED RESOLVED` |

### `VDDAI-REV-001`

The offline builder verifies unique sample IDs and canonical resolved image
paths across the whole manifest before replay. It confines paths to the
dataset root. The resulting replay still selects only normal validation and
does not require existing official-test files.

In a fresh isolated fixture, the reviewer matched package lineage to each
input manifest fingerprint and independently tried a shared train and
validation ID, a shared path with different IDs, and a normalized path alias
shared with a test record. The builder rejected all three before the first
extractor invocation. A disjoint matching manifest produced all 30 normal
validation observations with its official-test image absent. See
`ml/build_quality_reference.py` lines 23-40 and 48-77.

### `VDDAI-REV-002`

The shared image reader captures original mode from the same Pillow image
before conversion. Offline replay compares the captured source mode with the
manifest record alongside the existing format and dimension checks.
Production RGB conversion, tensor construction, timing, and scoring follow
the established path.

The reviewer replaced one RGB PNG with an L-mode PNG at the same path and
dimensions. The original matched manifest was rejected. Restoring the
original RGB fixture produced an identical aggregate. The frozen inference
and preprocessing tests passed. See
`app/services/image_preprocessing_service.py` lines 85-90 and 159-163 and
`ml/build_quality_reference.py` lines 83-100.

No new actionable findings surfaced.

## 5. Acceptance coverage

| Criterion | Evidence |
| --- | --- |
| Validated formats, original dimensions, basic RGB statistics, score distribution, and package identity | R1 verified upload and private aggregate evidence. All monitoring hooks and schema are unchanged in R2. Focused quality, preprocessing, inference, and metrics tests passed on R2. |
| Matched reference, bounded windows, and provisional threshold behavior | The original monitoring logic remains hash-identical and focused window and synthetic comparison tests passed. The split identity and source mode closures protect the verified reference path. |
| Aggregate privacy and frozen serving contract | Monitoring retains minute counts, scalar sums, and finite bins. The two remediations validate offline references and add original mode metadata without changing model inputs or exposing the mode as a metric. |
| Lightweight report and operator evidence | The report still reads one captured scrape. Documentation follows the eligible QA gate. |

## 6. Checks run

- Git branch, `HEAD`, ancestor, empty index, `git diff --check`, and SHA-256
  checks matched the exact eleven-file subject and preserved R1 report.
- Created a disposable `git archive --format=tar HEAD` snapshot, then
  overlaid and hash-checked the reviewed files. A cloned pinned Windows
  Python 3.14.3 runtime loaded the archive, with separate SQLite data, no
  inherited `GIT_*` overrides, and Torch-related thread counts capped at one.
- The independent split and mode probes described in section 4 passed.
- `python -B -m pytest -q -p no:cacheprovider --tb=short --show-capture=no
  --basetemp <scratch-directory> app/tests/test_quality_monitor.py
  app/tests/test_anomaly_inference_service.py
  app/tests/test_image_preprocessing_service.py app/tests/test_observability_metrics.py`
  reported **38 passed in 28.07 seconds**.
- The Coder reported **450 passed** for the canonical gate and **172 passed**
  in the strict PostgreSQL 16.15 gate with zero skips. The Coder also rebuilt
  the real 46-row normal-validation reference. Independent SHA-256 comparison
  confirmed both real reference files are identical at
  `e1ee5733a73c1f1bdafa9e119399657dd7c5ad78b4c4653ddb4cb89f88bef282`.
  The real package replay and database gates are corroborating Coder evidence.

## 7. Checks deferred

Independent strict PostgreSQL and any further real-package replay are QA
work. Hosted CI and live staging sit outside this review's local scope.

## 8. Handoff

Independent QA may verify the exact fingerprinted range, including both
closure cases, privacy and frozen inference regressions, and the local
reference evidence. Documentation follows a current QA pass.

## 9. Residual context

The current manifest contract identifies canonical records and configuration.
It does not include content digests for each image. The reference replay
now checks recorded split and metadata conflicts within that contract.
Operator warnings compare aggregate observations to normal validation.
A production promotion decision requires its separate human gate.

## Process-learning evidence

| Field | Record |
| --- | --- |
| Observation | A lineage-matched alias fixture showed that duplicate detection occurs before any extraction. A mode-only substitution proved the same image-open metadata reaches the replay boundary. |
| Evidence | Independent `VDDAI-REV-001` and `VDDAI-REV-002` closure checks. |
| Impact | The reviewer verified split separation and replay metadata without altering the established inference or dataset contract. |
| Recurrence | First observed in this re-review. |
| Candidate improvement | Keep reference closure checks explicit about zero inference before rejecting overlapping splits. |
| Authority note | This evidence confers no authority to change the workflow or its skills. |
