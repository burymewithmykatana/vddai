# Agent-Readiness A1-A10 Independent Review

- Review date: 2026-08-10
- Repository: VDDAI backend
- Review base: `origin/master` at `49a5b58`
- Local branch: `master`
- Final verdict: **CHANGES REQUIRED**

## Review Scope

The review covered the complete local A1-A10 agent-readiness change set,
including committed-base comparison, staged changes, unstaged changes, ordinary
untracked files, and relevant ignored documentation. The review was performed
against the repository-root `AGENTS.md`, the nested `app/AGENTS.md` and
`ml/AGENTS.md` instructions, the accepted architecture decision records, and
the Week 6 invariants for explicit experiment tracking, registration,
human-controlled promotion, serving resolution, immutable lineage, and the
frozen Week 5 inference contract.

At review time:

- the branch matched `origin/master`; there were no additional local commits;
- there were no staged changes;
- 49 tracked files had unstaged changes;
- 12 ordinary untracked files contained the ten logical readiness deliverables;
- relevant ignored documentation included seven files under `docs/`;
- no substantive API, authorization, database, worker, inference, ML,
  preprocessing, scoring, threshold, artifact-schema, or promotion behavior had
  changed.

No separately versioned A1-A10 specification was found in the repository. The
acceptance mapping therefore used the ten logical deliverables present locally:
root instructions, application instructions, ML instructions, issue template,
pull-request template, bootstrap script, verification script, CI workflow,
ML-change skill, and independent-review skill.

## Findings

### MEDIUM — Repository-wide line-ending churn fails diff hygiene

Exact examples include `.gitignore:1`, `app/api/deps.py:1`,
`artifacts/metrics.json:1`, `data/metadata/mvtec_ad_tile.json:1`, and line 1 of
both `.agents/skills/*/agents/openai.yaml` files.

The 49 tracked files reported 5,789 additions and 5,789 deletions, while
`git diff --ignore-space-at-eol` produced no patch content. `git diff --check`
exited with status 2 and reported trailing whitespace caused by CRLF rewrites.
The two new skill metadata files had the same issue.

This obscures the intended A1-A10 change set, touches unrelated application,
ML, test, documentation, metadata, and legacy-artifact files, and violates the
small, independently reviewable diff requirement in `AGENTS.md:114` and
`AGENTS.md:286`. The unrelated tracked files should be restored to their base
line endings, the new YAML files normalized, and an explicit `.gitattributes`
policy considered.

### MEDIUM — The canonical verification gate does not enforce the pinned environment

At `scripts/verify.ps1:28-48`, the script falls back to any `python`, prints its
version without validating it, and runs only `pip check`. `pip check` validates
dependency compatibility but does not prove that installed versions match the
exact `requirements.txt` pins. Consequently, an unsupported Python version or
drifted dependency set can produce `VDDAI verification passed`.

This conflicts with `AGENTS.md:217-218` and with the exact Python and pip checks
already present in `scripts/bootstrap.ps1:10-17` and
`scripts/bootstrap.ps1:58-117`. The verification gate should require the
validated repository environment or independently enforce the required Python
version and installed dependency pins.

### MEDIUM — The documentation source of truth is globally ignored

`.gitignore:31` ignores all of `docs/`, while `AGENTS.md:80`,
`AGENTS.md:90-93`, `AGENTS.md:118-120`, and `AGENTS.md:287-288` make accepted
ADRs authoritative and require durable decisions to be documented.

The rule already hides seven local documentation files, including
`docs/decisions/0002-anomaly-baseline-and-pytorch-data-contract.md`. A new Week
6 ADR, task specification, or review record will not appear in ordinary
`git status` or diff inspection and can be omitted silently. Ignore rules
should be narrowed to generated documentation, or maintained architecture,
decision, task, and review paths should be explicitly unignored.

### LOW — The change set is being developed directly in the master worktree

The working branch was `master`, contrary to `AGENTS.md:296-302` and
`.github/ISSUE_TEMPLATE/agent-task.md:90-95`. No commit or push had occurred,
so the state remained recoverable. The work should be moved to a task-specific
branch or worktree before committing.

### LOW — Root verification instructions are duplicated

`AGENTS.md:215-277` and `AGENTS.md:326-346` contain overlapping verification
guidance. The sections currently agree, but two authoritative copies create a
future drift risk. They should be consolidated.

## Acceptance-Criteria Coverage

| Logical area | Coverage |
|---|---|
| A1 root agent instructions | Partial: comprehensive, but verification is duplicated and conflicts with the ignored documentation source of truth |
| A2 application instructions | Covered: consistent with current API, worker, security, persistence, and inference contracts |
| A3 ML instructions | Covered: preserves split isolation, preprocessing, scoring, lineage, artifact validation, and the human promotion gate |
| A4 agent task template | Covered |
| A5 pull-request template | Covered |
| A6 bootstrap script | Statically covered: exact Python and pip checks plus non-destructive `.env` handling are present |
| A7 verification script | Partial: does not prove use of the pinned environment |
| A8 CI workflow | Statically covered: restricted permissions, pinned Python and pip, dependency checks, tests, Alembic graph read, and Docker build are defined |
| A9 ML-change skill | Covered |
| A10 independent-review skill | Covered |

## Checks Run

| Check | Outcome |
|---|---|
| Root, nested, skill, ADR, and relevant documentation inspection | Completed |
| `git status --short --branch` and staged/unstaged/untracked reconciliation | Completed; no staged changes, 49 unstaged tracked files, 12 ordinary untracked files |
| Relevant ignored-untracked documentation inspection | Completed; seven maintained-looking documentation files identified |
| Full diff, stat, line-ending, and file-type inspection | Completed |
| `git diff --check` | Failed with exit status 2 because of CRLF/trailing-whitespace findings |
| `git diff --ignore-space-at-eol` | Produced zero bytes of tracked patch content |
| YAML parsing for CI and skill metadata | Passed |
| JSON parsing for touched JSON files | Passed |
| Skill front-matter validation | Passed |
| AST parsing for 37 modified Python files | Passed under system Python 3.12 |
| Requirements encoding and exact-pin inspection | Passed; 73 exact pins found |
| Secret-pattern and new-file-size scan | No suspect secret or large new binary found |
| `docker compose -f docker-compose.yaml config --quiet` | Not completed; sandboxed and approved retry both failed with `/usr/bin/docker: Input/output error` |

## Checks Not Run

- `scripts/bootstrap.ps1` and `scripts/verify.ps1` were not executed because
  PowerShell was unavailable, the Windows `.venv` executable could not run from
  the WSL session, and bootstrap would mutate the local environment.
- The pytest suite and canonical verification gate were not run under the
  review's read-only-check constraint because they create local SQLite, cache,
  and runtime files.
- Docker image building and GitHub Actions execution were not run because they
  are mutating or externally hosted checks.

## Residual Risks and Assumptions

- PowerShell runtime behavior remains unverified.
- The GitHub-hosted CI workflow has not executed against this change set.
- Docker Compose configuration validation remains unavailable because of the
  local Docker executable failure.
- The complete Python test suite was not executed during this read-only review.
- The A1-A10 numbering is an artifact-based mapping because no separate formal
  A1-A10 specification was available locally.
- The broad `docs/` ignore rule means this review record itself is ignored until
  the repository ignore policy is corrected or the file is deliberately added.
- No production model registration, promotion, rollback, deployment, data
  mutation, commit, push, or merge was performed.

## Final Verdict

**CHANGES REQUIRED**
