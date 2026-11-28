# W9D3 input and model-quality monitoring review

## 1. Reviewed subject

Review `W9D3-REV-2026-11-27-001`, 27 November 2026. Independent review of
`codex/w9d3-quality-monitoring` in the W9D3 worktree. The approved base and
`HEAD` are `bd7feaff15038c345cf1a5a324d83aca4c53e3cf`. The merge base with
`origin/master` is `1b9f6160883361bdb99298b256815197ccab8eba`. The task-relative
committed and staged ranges are empty. Seven modified and four untracked
Python files form the reviewed subject. The review record is audit evidence
outside that implementation range.

| Reviewed file | SHA-256 |
| --- | --- |
| `app/api/routes/prediction.py` | `5d2064f09e9e3e02f025f7a6c7cc55c998f2f60d0cb98d5aacd6966873185f20` |
| `app/core/config.py` | `f94755fbf1ca45317a60068d2562f66a3064049a9fc6f785a5f4917f1250fae1` |
| `app/services/anomaly_inference_service.py` | `0277e4735df375ce5bf4219a979c392a715d44eb93829e71479de7261eebc068` |
| `app/services/image_preprocessing_service.py` | `4678c96a8ba4a82c8ba3b81d1656d280b9dfa2a2faccb07f9c867949f9cf325e` |
| `app/services/metrics_service.py` | `bd077f92554a9ff1c0602995a0e9471aa42012c87084bf6376e5c461c5a5261f` |
| `app/services/quality_monitor.py` (untracked) | `e1af34e7ceb9dd705d003e6b4b43ceaa66d57d6b5bb8903e487cebefecac9688` |
| `app/tests/test_prediction_api.py` | `8425d8e3314ffd2c89daa46880d8ca2624ad2abd6bf867d4885115c2d14244ae` |
| `app/tests/test_quality_monitor.py` (untracked) | `62cd21f21387347426c4742b3d9176dae1d2de7f6a94abdcbeb71cfd47b7f379` |
| `app/workers/prediction_worker.py` | `79e846246cecd0fcd4f0f481f8fc73fc6ffd7a2cbcec230ad620210fe8c22bdd` |
| `ml/build_quality_reference.py` (untracked) | `704305765cd4a984fb0ad3d58cc6a52c74717fd55edbfdbb86a8d276007971cf` |
| `scripts/report_quality_shift.py` (untracked) | `49d1766d89de9a416c711b93e29a30c8ccf4d49c76d7d204ed1c14292d709a4a` |

## 2. Contract and acceptance criteria

The approved [W9D3 task](https://app.notion.com/p/3ac0ab50ef6781e8badced236afe36cb)
requires validated image formats, dimensions, pixel signals, score distributions,
and model identity, along with tested aggregate quality monitoring and a
lightweight report. The approved local plan uses a 60-minute bounded window and
30 matched reference and current observations. Missing and malformed
references, insufficient observations, mixed windows, and mismatched package,
manifest, or preprocessing identity suppress comparison. Provisional operator
warnings use mean delta at least 0.15, contrast delta at least 0.10, a format
share or anomaly rate shift of at least 20 percentage points, and nearest-rank
score p95 strictly above 1.5 times the reference. The synthetic reference mode
is limited to tests. Durable aggregate retention belongs to W9D4.

The [repository rules](../../AGENTS.md), [application rules](../../app/AGENTS.md),
[ML instructions](../../ml/AGENTS.md), and [agent workflow](../engineering/agent-workflow.md)
govern this review. The accepted [inference](../decisions/0003-production-inference-contract.md)
and [frozen package](../decisions/0004-production-model-package-loader.md)
contracts remain applicable. The manifest-derived reference must use the
separate normal-validation split and preserve recorded image lineage.

## 3. Verdict

**CHANGES REQUIRED.** The live quality aggregation and focused regression
checks passed. The offline builder accepts duplicate train and validation
identities and accepts decoded images with source modes that contradict their
matched manifest metadata.

## 4. Findings

### `VDDAI-REV-001` A matching fingerprint can pass with overlapping splits

**HIGH - OPEN.** `ml/build_quality_reference.py` lines 28-61 and
`ml/AGENTS.md` lines 79-85.

The builder matches the manifest fingerprint and checks for duplicate sample
IDs and paths only among the records selected as validation. A training record
can reuse a validation ID or path without reaching either duplicate check.
A matching fingerprint identifies this malformed manifest but cannot establish
that its splits are disjoint. The builder then labels its overlapping sample
set as `normal_validation`. Monitoring comparisons could therefore use a
baseline that includes training samples contrary to the ML contract.

With a loaded fixture package bound to the exact digest of each supplied
manifest, an independent 30-image reproduction added one train record sharing
a validation ID and then a train record sharing a validation image path.
Both variants produced a 30-sample `normal_validation` reference.

Verify disjoint sample IDs and image paths across the manifest splits before
replay. Keep validation selection restricted to eligible normal records and
leave official-test image bytes outside the reference flow. Closure requires
matched-manifest regressions for shared IDs and shared paths, plus the existing
valid reference with absent test images.

### `VDDAI-REV-002` Decoded source mode can disagree with matched lineage

**MEDIUM - OPEN.** `ml/build_quality_reference.py` lines 68-85 and
`app/services/image_preprocessing_service.py` lines 82-90 and 153-161.

Canonical manifest records contain original source mode as well as format
and dimensions. The builder verifies only format and dimensions from the
preprocessed observation. A replaced input can pass those checks while
disagreeing with its recorded source mode, and the output retains the same
manifest fingerprint even after its measured baseline changes.

The independent fixture generated a valid reference from RGB PNGs. It then
replaced one file with a grayscale PNG at the same path and dimensions. The
builder accepted the file against the unchanged RGB manifest record and
reported a different RGB pixel mean under the same fingerprint.

Verify the image's recorded source mode during normal-validation replay
without changing the production tensor, color conversion, or score contract.
Closure requires rejecting an image with matching path, size, and format
but mismatched mode, and preserving the valid matched replay and serving
regressions.

## 5. Acceptance coverage

| Criterion | Evidence and result |
| --- | --- |
| Track formats, original dimensions, normalized pixel statistics, score distribution, and package identity | The focused tests verified post-commit upload counts, image metadata and frozen prediction equivalence, aggregate bins, and private report output. |
| Bounded windows, matched baseline, and provisional shift warnings | Window expiry, model transitions, and missing and synthetic references were exercised. The independent score test verified p95 equality stays clear, one higher score in 30 stays clear, and two higher scores in 30 trigger. An exact 20-point format shift triggered. Baseline provenance remains open under `VDDAI-REV-001` and `VDDAI-REV-002`. |
| Keep monitoring data aggregate and protect the frozen behavior | Source review found minute buckets with bin counts and scalar sums and an observer outside the frozen inference timer. The public API and queue transaction boundaries remain in place. No deployment or retention changes are part of this subject. |
| Produce a local shift report and operator evidence | The report parses one captured scrape and verifies aggregate counts. The engineering guide and retention integration follow their existing QA and later-task gates. |

## 6. Checks run

- Git branch, base, merge base, index and diff inspection, `git diff --check`,
  and SHA-256 verification matched the exact eleven-file subject.
- Created a disposable `git archive --format=tar HEAD` snapshot, overlaid
  and hash-checked the changed files, and verified module origins from a
  cloned pinned Windows Python 3.14.3 runtime. The scratch runner used
  separate SQLite data and cleared inherited `GIT_*` overrides.
- `python -B -m pytest -q -p no:cacheprovider --tb=short --show-capture=no
  --basetemp <scratch-directory> app/tests/test_quality_monitor.py
  app/tests/test_prediction_api.py app/tests/test_observability_metrics.py`
  returned **60 passed in 39.20 seconds**. Torch thread counts were capped at one.
- The independent fixture checks proved both counterexamples and verified the
  exact score and format warning boundaries. Their filesystem writes were
  confined to the scratch runner.
- The Coder reported **446 passed** for the exact canonical gate on
  PostgreSQL 16.15 and **172 passed** for the strict production gate. The
  Coder also reported an offline replay of 46 normal-validation images
  and a controlled synthetic shift with all five warnings. The reviewer
  verified the bytes of those local reference and shift reports match the
  two Coder receipt hashes. The real inference run is Coder evidence.

## 7. Checks deferred

A second real-package replay and new strict PostgreSQL run are downstream
verification after an eligible re-review. Live staging and release activity
remain outside the local W9D3 acceptance scope.

## 8. Remediation handoff

1. Obtain human selection of the open findings.
2. Address the selected split identity and source metadata checks within the
   offline reference path. Verify the two reproductions, matched replay,
   privacy, and frozen inference behavior.
3. Submit the exact remediated range for independent numbered re-review.
   Preserve this immutable record. QA follows an eligible verdict.

## 9. Residual context

A manifest fingerprint identifies its canonical records and configuration.
The current accepted manifest format does not include per-image content
checksums. The findings concern readily verifiable conflicts in its recorded
split assignments and metadata. The aggregate warnings represent differences
from normal-validation observations. They do not supply defect labels or a
new promotion decision.

## Process-learning evidence

| Field | Record |
| --- | --- |
| Observation | A valid package-to-manifest hash match coexisted with invalid split or source metadata in controlled fixtures. |
| Evidence | `VDDAI-REV-001` and `VDDAI-REV-002` and the independent checks in section 6. |
| Impact | Matching fingerprints need semantic checks at the reference replay boundary. |
| Recurrence | First observed in quality reference review. |
| Candidate improvement | Check cross-split duplicates and decoded source metadata in matching-manifest regression cases. |
| Authority note | This evidence confers no authority to change the workflow or its skills. |
