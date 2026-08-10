# Agent-Readiness A1-A10 Independent Re-Review

- Review ID: `VDDAI-AGENT-READINESS-A1-A10-R2`
- Review date: 2026-08-10
- Task: independently re-review the A1-A10 agent-readiness remediation
- Prior report: `docs/reviews/2026-08-10-agent-readiness-a1-a10.md`
- Remediation record: `docs/reviews/2026-08-10-agent-readiness-a1-a10-remediation.md`
- Repository base: `origin/master` at `49a5b58c018602adfcf394c336528aec2cc13810`
- HEAD: `49a5b58c018602adfcf394c336528aec2cc13810`
- Branch: `chore/agent-readiness-a1-a10`
- Final verdict: **CHANGES REQUIRED**

## Scope and Working-Tree State

This re-review covered the complete current A1-A10 working-tree change set,
the immutable prior report, the remediation record, the repository-root and
nested agent instructions, relevant accepted ADRs and Week 5 task material,
the ten logical deliverables used by the prior review, and relevant ordinary
untracked documentation exposed by the `.gitignore` remediation.

Before this report was written:

- HEAD, `origin/master`, and their merge base were identical;
- there were no local commits beyond `origin/master`;
- there were no staged changes;
- `.gitignore` was the only modified tracked file, with exactly two deleted
  lines removing the broad `docs/` ignore rule;
- 21 files were ordinary untracked files: the A1-A10 deliverables, the prior
  review and remediation record, and maintained-looking documentation that had
  previously been hidden by the broad ignore rule;
- no application, API, authorization, database, worker, migration, inference,
  preprocessing, scoring, threshold, artifact, or promotion implementation was
  changed by this task.

No separately versioned A1-A10 specification was found. As in the prior
report, acceptance coverage therefore maps A1-A10 to: root instructions,
application instructions, ML instructions, issue template, pull-request
template, bootstrap script, verification script, CI workflow, ML-change skill,
and independent-review skill.

## Contract Sources Reviewed

- `AGENTS.md`, `app/AGENTS.md`, and `ml/AGENTS.md`
- `docs/reviews/2026-08-10-agent-readiness-a1-a10.md`
- `docs/reviews/2026-08-10-agent-readiness-a1-a10-remediation.md`
- accepted ADRs under `docs/decisions/`, especially ADRs 0002-0005
- `docs/tasks/week05.md`, `readme.md`, and
  `docs/data_to_model_pipeline.md`
- the A1-A10 scripts, templates, workflow, and skill files
- current implementation evidence in `ml/data/torch_dataset.py`,
  `ml/feature_extractor.py`, and `app/workers/prediction_worker.py`

The review preserved `VDDAI-REV-001` through `VDDAI-REV-005` and assigned the
next stable ID only to the newly discovered finding.

## Verdict

**CHANGES REQUIRED**

All five original findings are **VERIFIED RESOLVED**. One newly discovered
medium-severity documentation-contract defect, `VDDAI-REV-006`, remains open.
The newly visible data-lineage document contradicts the active preprocessing
and production-serving paths, so the current agent-readiness source corpus is
not yet safe to treat as mutually consistent.

## Complete Finding Status Summary

| Finding | Severity | Re-review status | Summary |
|---|---|---|---|
| `VDDAI-REV-001` | MEDIUM | **VERIFIED RESOLVED** | Repository-wide line-ending churn is gone |
| `VDDAI-REV-002` | MEDIUM | **VERIFIED RESOLVED** | Verification now fails closed on Python, pip, and requirement-pin drift |
| `VDDAI-REV-003` | MEDIUM | **VERIFIED RESOLVED** | Maintained documentation is no longer globally ignored |
| `VDDAI-REV-004` | LOW | **VERIFIED RESOLVED** | Work is on a task-specific branch |
| `VDDAI-REV-005` | LOW | **VERIFIED RESOLVED** | Root verification guidance has one authoritative section |
| `VDDAI-REV-006` | MEDIUM | **OPEN** | Data-lineage documentation contradicts active preprocessing and serving |

## Findings

### VDDAI-REV-006 - MEDIUM - Data-lineage documentation contradicts active preprocessing and serving

- Status: **OPEN**
- Location: `docs/data_to_model_pipeline.md:10-15`,
  `docs/data_to_model_pipeline.md:227-257`, and
  `docs/data_to_model_pipeline.md:355-379`
- Evidence: the document says the API worker still uses
  `mock_model_service`, says uploaded API images are not part of serving
  lineage, assigns ImageNet normalization to `TorchManifestDataset`, and says
  tensor values no longer remain in `[0, 1]` after that adapter. The active
  code says the opposite: `ml/data/torch_dataset.py:1-5` preserves the shared
  `[0, 1]` tensor contract, `ml/feature_extractor.py:135-157` owns ImageNet
  normalization, and `app/workers/prediction_worker.py:108-125` calls the real
  anomaly-inference service and persists its score, threshold, package ID, and
  latency. The root and ML instructions also make normalization ownership and
  Week 5 production serving explicit invariants.
- Failure scenario: an agent treating this newly visible lineage document as
  current architecture could normalize tensors twice, reintroduce or preserve
  a mock-serving assumption, or document incomplete serving lineage. That
  would create offline/online preprocessing skew or weaken the frozen Week 5
  production contract.
- Why this matters to VDDAI: preprocessing ownership, real frozen-package
  inference, and complete persisted lineage are production ML invariants. The
  A1-A10 task is intended to make agent work safer; contradictory repository
  guidance directly undermines that outcome.
- Required action: update `docs/data_to_model_pipeline.md` to describe the
  current split-aware tensor path, keep tensors in `[0, 1]` until the
  ResNet-18 extractor performs ImageNet normalization, and describe the real
  package-backed worker and persisted public-safe serving lineage. Remove the
  obsolete mock-service and ambiguous confidence wording. Do not change the
  executable contracts to match the stale document.
- Verification required to close: compare the revised text against
  `ml/data/torch_dataset.py`, `ml/data/torch_dataloader.py`,
  `ml/feature_extractor.py`, `app/services/anomaly_inference_service.py`,
  `app/workers/prediction_worker.py`, and ADRs 0003-0005; confirm no remaining
  `mock_model_service` serving claim or dataset-adapter normalization claim;
  run `git diff --check`; and inspect the complete documentation diff.

### VDDAI-REV-001 - MEDIUM - Repository-wide line-ending churn

- Status: **VERIFIED RESOLVED**
- Location: complete tracked and untracked A1-A10 change set
- Fresh evidence: only `.gitignore` has a tracked diff, reported as two
  deletions. `git diff --ignore-space-at-eol -- .gitignore` shows the same
  substantive removal. `git diff --check` and `git diff --cached --check`
  pass. Strict UTF-8 and trailing-whitespace inspection of all 21 untracked
  files passes. Both skill Markdown files and both `agents/openai.yaml` files
  contain zero CRLF sequences and no trailing whitespace.
- Failure scenario rechecked: the prior 49-file, 5,789-addition/5,789-deletion
  line-ending rewrite is no longer present; the intended change is reviewable.
- Why it matters to VDDAI: clean diffs preserve reviewability and prevent
  unrelated application, ML, test, and artifact changes from being hidden.
- Required action: none for this finding.
- Closure verification completed: tracked diff, ignored-EOL diff, whitespace
  checks, byte-level line-ending checks, and full status reconciliation.

### VDDAI-REV-002 - MEDIUM - Verification did not enforce the pinned environment

- Status: **VERIFIED RESOLVED**
- Location: `scripts/verify.ps1:11-15`, `scripts/verify.ps1:74-125`, and
  `scripts/verify.ps1:132-180`
- Fresh evidence: the default interpreter is the repository
  `.venv\\Scripts\\python.exe`; Python `3.14.3` and pip `26.1.2` are required;
  every non-comment requirement must use exact `name==version` syntax; package
  names are normalized; missing or mismatched packages cause failure before
  tests. Independent installed-metadata comparison found all 73 expected pins
  at the exact versions, and `pip check` passed. An actual invocation with
  Python `3.13.5` exited 1 at `scripts/verify.ps1:145`, before tests, with the
  required-version error. Both PowerShell scripts parse without errors under
  Windows PowerShell 5.1.
- Failure scenario rechecked: an unsupported Python version, pip version, or
  required-package version can no longer produce the final verification-pass
  message through the normal gate path.
- Why it matters to VDDAI: the canonical gate now verifies the reproducible
  toolchain and dependency set before trusting test results.
- Required action: none for this finding.
- Closure verification completed: static control-flow review, independent
  exact-pin comparison, `pip check`, script parser validation, and a real
  Python-version mismatch run. The full positive gate was not rerun in this
  review because it writes test database and pytest runtime files; that
  limitation is recorded below rather than treated as an unexecuted pass.

### VDDAI-REV-003 - MEDIUM - Documentation source of truth was globally ignored

- Status: **VERIFIED RESOLVED**
- Location: `.gitignore:24-41`
- Fresh evidence: the tracked diff removes only the broad `docs/` rule.
  `git ls-files --others --ignored --exclude-standard -- 'docs/**'` returns no
  files, while the prior report, remediation record, maintained ADR/task/data
  documentation, and product/architecture placeholders appear in ordinary Git
  status. Representative dataset, artifact, virtual-environment, pytest, and
  local-database paths remain ignored by their narrow rules.
- Failure scenario rechecked: new maintained ADRs, task specifications, and
  review records are now visible to ordinary status and diff preparation.
- Why it matters to VDDAI: agent and human review can now see the repository's
  durable decisions and handoff evidence.
- Required action: none for the ignore-policy defect. The newly visible stale
  content is a separate defect tracked as `VDDAI-REV-006`.
- Closure verification completed: ignore-rule diff inspection, ignored-docs
  query, ordinary untracked-file reconciliation, and representative generated
  output checks.

### VDDAI-REV-004 - LOW - Work was developed in the master worktree

- Status: **VERIFIED RESOLVED**
- Location: repository branch state
- Fresh evidence: `git status --short --branch --untracked-files=all` reports
  `chore/agent-readiness-a1-a10`; HEAD remains equal to `origin/master`; there
  are no local commits, staged changes, pushes, or merges.
- Failure scenario rechecked: the task is no longer being prepared directly
  on `master`.
- Why it matters to VDDAI: the work remains independently reviewable and
  cannot be mistaken for approved master history.
- Required action: none for this finding.
- Closure verification completed: branch, HEAD, origin base, merge base, log,
  staged state, and unstaged state inspection.

### VDDAI-REV-005 - LOW - Root verification instructions were duplicated

- Status: **VERIFIED RESOLVED**
- Location: `AGENTS.md:215-277`
- Fresh evidence: exact heading inspection finds one `## Verification`
  section and no second verification-like root heading. The single section
  covers the canonical gate, optional Docker configuration, focused Python,
  formatting, database, Docker, documentation-only checks, and truthful
  reporting of unavailable checks.
- Failure scenario rechecked: there are no longer two authoritative root
  verification sections that can drift independently.
- Why it matters to VDDAI: agents now have one unambiguous repository-wide
  verification contract.
- Required action: none for this finding.
- Closure verification completed: exact heading count and full section review.

## Acceptance-Criteria Coverage

| Logical area | Re-review coverage |
|---|---|
| A1 root agent instructions | Covered: complete, internally consistent, and one verification section |
| A2 application instructions | Covered: consistent with current API, worker, security, persistence, and inference contracts |
| A3 ML instructions | **Partial overall**: `ml/AGENTS.md` is correct, but newly visible `docs/data_to_model_pipeline.md` contradicts normalization ownership and serving state (`VDDAI-REV-006`) |
| A4 agent task template | Covered |
| A5 pull-request template | Covered |
| A6 bootstrap script | Covered: parser passes and `-CheckOnly` validates Python 3.14.3, pip 26.1.2, dependency health, and non-destructive `.env` preservation |
| A7 verification script | Covered for the original pinning defect: exact interpreter/tool/package checks and fail-closed mismatch behavior are verified |
| A8 CI workflow | Statically covered: YAML parses; restricted permissions, pinned Python/pip, dependency check, one Alembic head, full pytest command, and Docker image build are defined |
| A9 ML-change skill | Covered: structure/front matter parse and the skill preserves leakage, lineage, compatibility, and human-promotion gates |
| A10 independent-review skill | Covered: structure/front matter parse and the skill requires durable reports, stable IDs, write boundaries, closure evidence, and numbered re-reviews |
| Cross-cutting documentation and diff hygiene | **Not covered** until `VDDAI-REV-006` is resolved |

## Checks Run

| Exact command or check | Outcome |
|---|---|
| `git status --short --branch --untracked-files=all` | Task branch; one tracked edit; 21 untracked files before this report; no staged changes |
| `git rev-parse HEAD`, `git rev-parse origin/master`, `git merge-base HEAD origin/master`, and `git log --oneline origin/master..HEAD` | HEAD/base/merge base all `49a5b58...`; no local commits |
| `git diff --name-status`, `git diff --cached --name-status`, `git diff --stat`, and `git diff --numstat` | Only `.gitignore`, two deletions; staged diff empty |
| `git diff --check` and `git diff --cached --check` | Passed |
| `git diff --ignore-space-at-eol -- .gitignore` | Shows only removal of the broad `docs/` rule |
| Byte-level UTF-8, CRLF, NUL, and trailing-whitespace inspection of A1-A10 files | Passed; the four remediated skill files have zero CRLF and no trailing whitespace |
| Strict UTF-8, NUL, trailing-whitespace, file-size, and high-confidence secret-pattern scan of all 21 untracked files | Passed; no binary/encoding/whitespace/secret hit; largest file 27,252 bytes |
| `git ls-files --others --ignored --exclude-standard -- 'docs/**'` | No ignored documentation |
| `git check-ignore -v` on representative data, artifact, `.venv`, pytest, and database paths | Narrow generated/runtime ignore rules remain effective |
| Exact `## Verification` heading count in `AGENTS.md` | One |
| PowerShell AST parse of `scripts/bootstrap.ps1` and `scripts/verify.ps1` | Passed under Windows PowerShell 5.1 |
| PyYAML parse of `.github/workflows/ci.yml` and both skill metadata YAML files | Passed |
| YAML front-matter validation for both `SKILL.md` files | Passed |
| Requirements syntax inspection | 73 exact pins; zero unsupported lines |
| Independent `importlib.metadata` comparison against `requirements.txt` | 73 expected packages; zero version drift |
| `.venv\\Scripts\\python.exe -B -m pip check` | Passed: `No broken requirements found.` |
| `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\\bootstrap.ps1 -CheckOnly` | Passed; Python 3.14.3, pip 26.1.2, dependency health, existing `.env` preservation |
| `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\\verify.ps1 -PythonCommand C:\\Users\\S.R.G\\AppData\\Local\\Programs\\Python\\Python313\\python.exe` | Failed closed as expected with exit 1 before tests; Python 3.13.5 rejected |
| `.venv\\Scripts\\python.exe -B -m alembic heads` | Passed; one head, `20260803_02` |
| `docker compose -f docker-compose.yaml config --quiet` | Passed |
| Static comparison of `docs/data_to_model_pipeline.md` with tensor, extractor, worker, and ADR sources | Failed; produced new `VDDAI-REV-006` |

## Checks Not Run

- The full positive `scripts/verify.ps1` gate and `python -m pytest -q` were not
  rerun. The test configuration writes `test_vddai.db`, `.pytest_tmp`, pytest
  cache, and potentially other runtime files, while this re-review permits the
  report as the only repository write. The remediation record's 208-pass result
  is prior evidence, not a check claimed by this re-review.
- `python -m black --check .` was not run because no Python implementation was
  changed and the repository instructions document pre-existing Black baseline
  drift.
- `scripts/bootstrap.ps1` without `-CheckOnly` was not run because it installs
  packages and may create `.env`.
- Docker image building and container startup were not run because they mutate
  local Docker state. Compose configuration validation did run successfully.
- GitHub Actions was not executed because it is externally hosted. The workflow
  was reviewed and parsed statically only.
- No database upgrade/downgrade, model loading, dataset generation, artifact
  regeneration, production promotion, deployment, or other state-changing
  check was run because those behaviors are outside this instruction-only
  review and its write boundary.

## Ordered Remediation Handoff

1. **`VDDAI-REV-006` - correct the current data-lineage document.** Update only
   the stale sections of `docs/data_to_model_pipeline.md` so they agree with
   the shared `[0, 1]` tensor contract, extractor-owned ImageNet normalization,
   split-aware loader behavior, real package-backed worker inference, anomaly
   score terminology, and persisted serving lineage. This finding has no
   dependency on another open finding. Close it by comparing the document to
   the exact implementation and ADR sources listed in the finding, searching
   for remaining obsolete mock/normalization claims, running
   `git diff --check`, and inspecting the complete documentation diff. Run the
   canonical verification gate only in an implementation/remediation context
   where its ignored runtime writes are permitted.

There are no remaining remediation actions for `VDDAI-REV-001` through
`VDDAI-REV-005`.

## Residual Risks and Assumptions

- A1-A10 remains an artifact-based mapping because no independent formal
  A1-A10 specification was available in the repository or task input.
- Four newly visible documentation paths are zero-byte placeholders:
  `docs/architecture/system_requirement.md`,
  `docs/product/customer_discovery.md`,
  `docs/product/problem_statement.md`, and
  `docs/product/success_metrics.md`. They make no conflicting claims, but their
  intentional inclusion or exclusion should be decided before a future commit.
- The complete positive verification gate was not independently rerun under
  this review's report-only write boundary.
- The CI workflow has not yet produced hosted-run evidence for this uncommitted
  change set.
- The working-tree `.gitignore` is subject to the machine's global
  `core.autocrlf=true` conversion warning; Git's substantive and
  ignore-EOL diffs both remain limited to the intended two-line removal.
- No commit, push, merge, deployment, data mutation, model registration,
  production promotion, or rollback was performed.

## Final Verdict

**CHANGES REQUIRED**
