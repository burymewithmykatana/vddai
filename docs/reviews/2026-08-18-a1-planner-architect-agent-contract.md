# A1 Planner/Architect Agent Contract Review

- Review ID: `VDDAI-A1-PLAN-REVIEW-2026-08-18`
- Date: 2026-08-18
- Task: A1 - Define the VDDAI Planner/Architect agent contract
- Branch: `codex/feat/w7-planner-architect`
- Base: `origin/master` at `fa111787ea810cc2432d3b0b7cead1f0042d332e`
- Head: `fa111787ea810cc2432d3b0b7cead1f0042d332e`
- Reviewed state: two untracked A1 files; no committed, staged, or tracked unstaged A1 changes
- Verdict: **CHANGES REQUIRED**

## Scope

This review covers the complete current A1 implementation against
`origin/master`:

- `.agents/skills/vddai-plan/SKILL.md`
- `.agents/skills/vddai-plan/agents/openai.yaml`

The user-authorized A1 prompt at
`docs/archive/prompts/week07/A1 Planner-Architect Agent.md` is treated as the
task specification, not as implementation. The unrelated untracked
`docs/archive/VDDAI W7D1 — Durable Image Storage Boundary.md` file is excluded.
This review report is audit evidence and is excluded from the A1 implementation
scope.

## Contract Sources

- The user-supplied A1 acceptance criteria and important review requirements.
- `docs/archive/prompts/week07/A1 Planner-Architect Agent.md`, explicitly
  authorized by the user as the complete A1 task.
- Repository-root `AGENTS.md`.
- `docs/README.md` and `docs/catalog.yaml`.
- `.agents/skills/vddai-review/SKILL.md` and its `agents/openai.yaml`.
- `.agents/skills/vddai-ml-change/SKILL.md` and its `agents/openai.yaml`.
- `.github/ISSUE_TEMPLATE/agent-task.md` and
  `.github/pull_request_template.md` for task, branch, review, verification,
  and human-gate conventions.

## Verdict

**CHANGES REQUIRED**

The A1 skill is structurally valid, directly invokable, scope-bounded, and
strongly planning-only. It covers the required handoff topology and aligns
with repository documentation and Git workflow. One decision-policy gap can
cause the Planner either to escalate ordinary implementation design choices or
to leave repository-resolvable ambiguity unsettled. That gap undermines the
requirement to produce an implementation-ready Coder handoff without redesign.

## Findings

### VDDAI-REV-001 - Ambiguity escalation does not protect planner-owned design decisions

- Severity: `MEDIUM`
- Status: `OPEN`
- Location: `.agents/skills/vddai-plan/SKILL.md:33-39` and
  `.agents/skills/vddai-plan/SKILL.md:65-78`
- Evidence: Lines 33-38 require repository inspection and contract
  reconciliation, lines 65-76 require the Planner to select a coherent
  implementation design, and line 78 correctly stops at an unapproved
  fundamental architecture decision. However, line 39 separately requires a
  stop whenever a missing decision would materially change broad categories
  including persistence, compatibility, or operations. It does not explicitly
  direct the Planner to (1) resolve ambiguity established by authoritative
  repository evidence, (2) decide ordinary implementation details within an
  approved scope and existing architecture, and (3) escalate only product
  changes, fundamental or durable architecture choices, and existing human
  approval gates. Normal design choices can affect persistence or operations,
  so the current broad rule can trigger premature escalation despite the
  design responsibility assigned later in the skill.
- Failure scenario: An approved task fixes the outcome and existing contracts
  but leaves a repository-pattern-level choice, such as which existing service
  owns validation or how an already-approved record is represented. Repository
  inspection supplies enough evidence for the Planner to choose and document
  the smallest design. The current wording can classify the choice as a
  persistence or operations decision and stop, leaving the Coder to redesign
  the solution or wait for unnecessary approval.
- Why it matters: A1 exists to remove design work from the Coder handoff while
  preserving meaningful human architecture gates. An overbroad or incomplete
  decision policy weakens both objectives and does not fully satisfy important
  review requirement 9.
- Required action: Add an explicit three-way decision policy. Require the
  Planner to resolve ambiguity from authoritative repository evidence when the
  answer is established; allow the Planner to choose and justify ordinary
  implementation details that remain within approved scope, current contracts,
  and existing architecture; and require escalation for product-requirement
  changes, unresolved fundamental or durable architecture decisions, or a
  human gate defined by `AGENTS.md`. Narrow or qualify line 39 so broad area
  names alone do not force escalation.
- Verification required: Rerun skill and metadata validation, then exercise
  the skill against three read-only planning scenarios: one repository-
  resolvable ambiguity, one ordinary implementation design choice, and one
  unapproved fundamental architecture decision. Confirm that the first two
  produce a reasoned design in the Coder handoff and the third stops with a
  precise human approval request. Perform an independent re-review preserving
  `VDDAI-REV-001`.

No other actionable correctness, scope, metadata, documentation-routing,
security, database, worker, ML-integrity, or Git-workflow findings were found.

## Acceptance-Criteria Coverage

| Acceptance criterion | Implementation evidence | Verification evidence | Result |
| --- | --- | --- | --- |
| Repository-level Planner/Architect skill exists | `vddai-plan/SKILL.md` and `agents/openai.yaml` follow the two existing VDDAI skill layouts | Scoped Git status shows exactly the two expected A1 files; skill validator passes | Pass |
| Consumes an approved task plus current repository context | `SKILL.md:8-12` establishes the approved-task flow; `SKILL.md:33-41` requires task, repository, contract, documentation, ADR, implementation, test, migration, schema, configuration, and Git inspection | Static inspection against `AGENTS.md`, docs routing, and existing skills | Pass |
| Requires bounded scope, affected components, invariants, acceptance criteria, verification, risks, documentation, and Coder handoff | `SKILL.md:43-63` and the eleven required sections at `SKILL.md:84-150` | Required-content and heading checks pass | Pass |
| Prohibits production implementation, silent scope expansion, and unapproved architecture/product decisions | `SKILL.md:14-29` establishes a read-only boundary, explicit prohibitions, and a human handoff before implementation | Static prohibition review | Pass |
| Consistent with `AGENTS.md` | `SKILL.md:12`, `34-41`, `63`, `121-123`, and `131-133` inherit repository authority, validation truthfulness, and human gates without weakening them | Comparison with complete root `AGENTS.md` | Pass |
| Consistent with current documentation routing | `SKILL.md:35` starts at `docs/README.md` and `docs/catalog.yaml`; `SKILL.md:125-127` keeps repository docs authoritative and conditions ADR work | Referenced paths exist and match the documented authority order | Pass |
| Consistent with branching/review workflow | `SKILL.md:10`, `37`, `133`, and `164` preserve task branch/worktree isolation, plan approval, independent review, and human merge approval | Comparison with agent-task and pull-request templates; branch equals reviewed `origin/master` base | Pass |
| Directly invokable for future tasks | Frontmatter names `vddai-plan`; `openai.yaml` default prompt explicitly starts with `Use $vddai-plan` | YAML parse and invocation assertion pass | Pass |
| Coder handoff is usable without the planning conversation | `SKILL.md:135-150` requires a standalone objective, full scope boundaries, sequence, criteria, checks, docs, risks, gates, paths, contracts, and approved decisions | Static structure is complete, but decision-policy behavior can leave normal design unresolved | Partial - `VDDAI-REV-001` |
| Decision behavior distinguishes resolvable ambiguity, planner-owned detail, and human-gated architecture | Inspection, design, and fundamental-architecture rules exist at `SKILL.md:33-39` and `65-78` | Static scenario analysis exposes overlap between line 39 and planner design responsibility | Fail - `VDDAI-REV-001` |

## Checks Run

| Command or check | Outcome |
| --- | --- |
| `Get-Content -LiteralPath .\AGENTS.md -Raw` | Passed; root instructions read first and completely |
| Complete reads of the A1 task, both A1 files, both existing VDDAI skills and metadata, docs routing, issue template, and PR template | Passed |
| `git rev-parse HEAD`, `git rev-parse origin/master`, and `git merge-base HEAD origin/master` | All resolved to `fa111787ea810cc2432d3b0b7cead1f0042d332e` |
| `git diff --name-status origin/master...HEAD` | Passed; no committed A1 range |
| `git diff --name-status` and `git diff --cached --name-status` | Passed; no tracked unstaged or staged changes |
| `git status --short --untracked-files=all -- .agents/skills/vddai-plan` | Passed; exactly the two expected A1 files |
| `git diff --no-index -- NUL <A1 file>` for both files | Complete new-file content inspected; only the expected files were present |
| `python C:\Users\S.R.G\.codex\skills\.system\skill-creator\scripts\quick_validate.py .\.agents\skills\vddai-plan` | Passed: `Skill is valid!` |
| Python/PyYAML assertions for `openai.yaml` keys, display name, short-description length, and `$vddai-plan` default-prompt prefix | Passed |
| PowerShell checks for required paths, eleven numbered handoff sections, required scope and analysis content, and absence of `TODO` | Passed |
| PowerShell trailing-whitespace and final-newline checks for both A1 files | Passed |
| Initial composite PowerShell status filter | The file-content checks passed, but the isolation filter script failed because Git quoted two unrelated archive filenames; the scoped Git-status check above corrected the filter and passed |
| PowerShell review-report formatting and concrete path-reference check | The first unresolved-marker predicate produced a false positive because the report describes the absence of `TODO`; the corrected placeholder predicate passed, as did whitespace, final-newline, and path-existence checks |

## Checks Not Run

- `python scripts/validate_docs.py` was not run because the A1 implementation
  changes `.agents/skills/`, not maintained `docs/` content. This review report
  is audit evidence and is outside the implementation scope.
- `./scripts/verify.ps1`, pytest, Black, Alembic, and Docker checks were not run
  because A1 changes only agent instructions and metadata and does not alter
  executable application, database, ML, or infrastructure behavior.
- A live forward-test of `$vddai-plan` was not run. The open decision-boundary
  finding should be remediated before that scenario test is treated as closure
  evidence.
- Hosted CI was not run because the A1 files and this report are uncommitted and
  unpushed.

## Ordered Remediation Handoff

1. `VDDAI-REV-001`: In `.agents/skills/vddai-plan/SKILL.md`, define the three-
   way decision policy for repository-resolvable ambiguity, planner-owned
   implementation detail, and human-gated product or fundamental architecture
   decisions. Qualify the broad escalation rule at line 39. Do not change the
   planning-only write boundary, the eleven-section handoff, or unrelated
   repository instructions.
2. Rerun the skill validator, metadata assertions, required-content checks, and
   whitespace checks.
3. Run the three read-only decision scenarios described in the finding and
   retain their outputs as re-review evidence without implementing product
   changes.
4. Request an independent re-review. Write a new numbered report such as
   `docs/reviews/2026-08-18-a1-planner-architect-agent-contract-r2.md`; preserve
   `VDDAI-REV-001` and mark it `VERIFIED RESOLVED` or `STILL OPEN` with fresh
   evidence.

## Residual Risks and Assumptions

- The local `origin/master` reference was used as requested; no fetch was
  performed. The branch head, merge base, and `origin/master` all matched at
  review time.
- The A1 task prompt is untracked archive content but was explicitly elevated
  by the user as the authoritative task specification for this review.
- `vddai-plan` and `vddai-ml-change` have overlapping implicit applicability for
  ML planning. Explicit `$vddai-plan` invocation and its stricter planning-only
  boundary make the intended role clear; no current conflict was found.
- `SKILL.md:76` repeats one model-selection invariant from `AGENTS.md`. This is
  narrow and consistent rather than conflicting, so it is not an actionable
  finding, but future edits should avoid broader duplication drift.
- No implementation, test, migration, configuration, or production state was
  modified. No commit, push, merge, deployment, model action, or data mutation
  occurred.
