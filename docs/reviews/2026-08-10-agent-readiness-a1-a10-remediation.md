# Agent-Readiness A1-A10 Remediation Record

- Remediation date: 2026-08-10
- Source review: `docs/reviews/2026-08-10-agent-readiness-a1-a10.md`
- Review verdict received: `CHANGES REQUIRED`
- Repository base: `origin/master` at `49a5b58c018602adfcf394c336528aec2cc13810`
- Remediation branch: `chore/agent-readiness-a1-a10`
- Commit, push, merge, deployment, and model promotion: not performed

## Scope

This record maps stable IDs onto the five findings in the source review and
records the remediation evidence available to an independent re-reviewer. The
source review remains unchanged as immutable evidence.

## Finding Dispositions

### VDDAI-REV-001 — Repository-wide line-ending churn

- Original severity: `MEDIUM`
- Remediation status: `ADDRESSED — RE-REVIEW REQUIRED`
- Action: unrelated tracked-file line-ending churn was removed before this
  remediation phase. The remaining new skill Markdown and YAML files were
  normalized to LF.
- Evidence:
  - `git status --short --branch --untracked-files=all` reports one intentional
    tracked change, `.gitignore`, rather than the 49 unrelated tracked files in
    the source review;
  - `git diff --check` passes;
  - byte inspection reports zero CRLF sequences in both skill `SKILL.md` files
    and both `agents/openai.yaml` files.
- Policy decision: no `.gitattributes` policy was added. Introducing a
  repository-wide normalization policy in this task could create a broad
  renormalization diff. The current remediation keeps the change set narrow.
- Closure check: independently inspect tracked and untracked diffs for
  line-ending-only churn and whitespace errors.

### VDDAI-REV-002 — Verification did not enforce the pinned environment

- Original severity: `MEDIUM`
- Remediation status: `ADDRESSED — RE-REVIEW REQUIRED`
- Action: `scripts/verify.ps1` now:
  - requires the repository `.venv` by default instead of falling back to an
    arbitrary `python` command;
  - requires Python `3.14.3`;
  - requires pip `26.1.2`;
  - parses every non-comment requirement as an exact `name==version` pin;
  - compares all required packages against installed package metadata;
  - retains `pip check`, full pytest, optional formatting, and optional Docker
    Compose configuration validation.
- Positive evidence: `scripts/verify.ps1 -IncludeDockerConfig` validated Python,
  pip, all 73 requirement pins, dependency health, 208 tests, and Docker Compose
  configuration successfully.
- Negative evidence: invoking the gate with Python `3.13.5` failed before tests
  with an explicit Python `3.14.3` requirement error.
- Implementation note: an initial Windows PowerShell 5.1 JSON-array parsing
  incompatibility was observed, corrected, and followed by the successful full
  verification run.
- Closure check: independently inspect the pin comparison and repeat the
  positive and version-mismatch checks.

### VDDAI-REV-003 — Documentation source of truth was globally ignored

- Original severity: `MEDIUM`
- Remediation status: `ADDRESSED — RE-REVIEW REQUIRED`
- Action: removed the broad `docs/` rule from `.gitignore`. Generated datasets,
  model artifacts, caches, and other existing generated-output rules remain
  ignored.
- Evidence:
  - `git ls-files --others --ignored --exclude-standard -- 'docs/**'` returns no
    files;
  - the original review, this remediation record, ADRs, task documentation,
    architecture notes, and product documentation are visible to ordinary Git
    status inspection.
- Existing-file note: previously ignored documentation files were not edited by
  this remediation merely because they became visible. They remain available
  for an intentional inclusion decision before commit.
- Closure check: confirm maintained documentation and review reports appear in
  ordinary Git status while generated runtime artifacts remain ignored.

### VDDAI-REV-004 — Work was developed in the master worktree

- Original severity: `LOW`
- Remediation status: `ADDRESSED — RE-REVIEW REQUIRED`
- Action: moved the uncommitted working tree to
  `chore/agent-readiness-a1-a10`.
- Evidence: `git status --short --branch` identifies the task branch; no commit,
  push, or merge was performed.
- Closure check: confirm the active branch and base before committing.

### VDDAI-REV-005 — Root verification instructions were duplicated

- Original severity: `LOW`
- Remediation status: `ADDRESSED — RE-REVIEW REQUIRED`
- Action: consolidated the root instructions to one complete `## Verification`
  section.
- Evidence: exact heading-count validation reports one root verification
  section.
- Closure check: inspect the root instructions for completeness and absence of
  duplicated verification guidance.

## Additional Post-Review Improvement

The `vddai-review` skill was updated after the source report demonstrated that a
chat-only review is not a sufficient asynchronous handoff. It now requires a
durable review report, stable finding IDs, closure checks, an ordered remediation
handoff, immutable prior reports, and numbered re-review reports.

Both repository skills pass the skill structure validator after these changes.

## Verification Evidence

| Check | Result |
|---|---|
| PowerShell parser for `scripts/verify.ps1` | Passed |
| Canonical gate with `-IncludeDockerConfig` | Passed |
| Required Python version | `3.14.3` validated |
| Required pip version | `26.1.2` validated |
| Exact requirements pins | 73 pins validated |
| `pip check` | Passed |
| Full pytest suite | 208 passed |
| Docker Compose configuration | Passed |
| Python 3.13 fail-closed check | Rejected as expected |
| `git diff --check` | Passed |
| Ignored files under `docs/` | None |
| `vddai-review` structure validation | Passed |
| `vddai-ml-change` structure validation | Passed |
| Root verification heading count | Exactly one |

Formatting was not included in the canonical gate because the repository has a
documented pre-existing Black baseline drift. No unrelated Python files were
reformatted.

## Re-Review Handoff

Run a fresh independent review against the current branch and write:

`docs/reviews/2026-08-10-agent-readiness-a1-a10-r2.md`

The re-review must preserve IDs `VDDAI-REV-001` through `VDDAI-REV-005`, mark
each `VERIFIED RESOLVED`, `STILL OPEN`, or `ACCEPTED RISK`, add IDs for any new
findings, and issue a new final verdict. The re-review must not modify
implementation or remediation files.
