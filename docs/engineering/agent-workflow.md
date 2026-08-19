# Agent Handoff and Workflow Contract

- Status: Current
- Last reviewed: 2026-08-19
- Scope: human-controlled VDDAI planning, implementation, review, QA,
  documentation, and merge handoffs

## Purpose and Authority

This document composes the repository role contracts into one manual
development lifecycle. It defines cross-role handoffs, evidence freshness,
backward routing, and human approval gates. It does not replace a role's own
entry contract, output schema, authority, or write boundary.

Apply authority in this order:

1. [`AGENTS.md`](../../AGENTS.md) defines repository-wide invariants, Git rules,
   verification requirements, and human-controlled actions.
2. The role skills define the complete inputs, outputs, statuses, and operating
   boundaries owned by each role.
3. This document defines how those existing role-owned contracts connect.

If this document conflicts with `AGENTS.md` or a role skill, stop and report the
conflict. Do not weaken the higher-authority contract to keep work moving.

This is a procedural contract. It does not create an autonomous agent system,
a runtime state machine, an orchestration service, or permission to introduce
LangChain, CrewAI, a workflow engine, or another coordination dependency.

## Standard Lifecycle

The standard lifecycle for a repository implementation change is:

```text
Human-approved task
  -> Planner/Architect
  -> human plan approval
  -> Coder/Developer
  -> independent Reviewer
  -> human-selected remediation and independent re-review when required
  -> independent QA/Test
  -> Documentation
  -> human merge decision
```

An artifact's existence is not approval. A successful implementation, review,
QA run, Documentation pass, CI run, or pull request does not authorize the next
human-gated action unless the required approval is explicit.

## Role Ownership

| Role | Owns | Must not do |
|---|---|---|
| [Planner/Architect](../../.agents/skills/vddai-plan/SKILL.md) | Repository inspection, scope, design decisions within approved boundaries, acceptance mapping, verification planning, and the standalone Coder handoff | Implement, silently make a human-gated decision, or treat plan completion as approval |
| [Coder/Developer](../../.agents/skills/vddai-code/SKILL.md) | The approved implementation or approved remediation, implementation tests and checks, and the standalone implementation report | Redesign scope, close review findings, independently review, merge, deploy, or perform a protected action |
| [Reviewer](../../.agents/skills/vddai-review/SKILL.md) | Independent review, immutable reports, `VDDAI-REV-*` findings, closure checks, finding status, and the review verdict | Implement fixes, mutate reviewed files other than its new report, or authorize merge |
| [QA/Test](../../.agents/skills/vddai-qa/SKILL.md) | Independent behavioral verification, criterion evidence, `QA-SCN-*`, `QA-DEF-*`, `QA-REF-*`, and `PASS`/`FAIL`/`BLOCKED` classification | Fix defects, change permanent tests or requirements, duplicate Reviewer findings, or accept new risk |
| [Documentation](../../.agents/skills/vddai-documentation/SKILL.md) | Truthful durable documentation for the eligible reviewed and QA-verified implementation, documentation-only validation, and its standalone report | Change implementation, tests, requirements, review evidence, or represent later prose as QA-tested |

For ML, data, lineage, or artifact changes, apply
[`$vddai-ml-change`](../../.agents/skills/vddai-ml-change/SKILL.md) alongside the
applicable Planner or Coder role. It is a domain-safety companion, not a new
lifecycle stage.

## Handoff Artifacts

The owning role skill remains authoritative for each artifact's full schema.
The requirements below identify the minimum cross-role identity and evidence
that the receiving role must be able to consume; they do not define a parallel
report format.

### Approved task

The Planner receives an identifiable human-approved task containing the
objective, exact acceptance criteria, `IN SCOPE`, `OUT OF SCOPE`, `MUST
PRESERVE`, supplied evidence, intended base when known, and applicable human
gates. Missing or contradictory requirements must be resolved or explicitly
blocked rather than inferred from implementation or tests.

### Planner handoff and human approval

The Planner returns the eleven-section result required by `$vddai-plan`, ending
with a standalone Coder handoff. It records the inspected repository state and
base, resolved repository facts, planner-owned decisions, any human-gated
decision, implementation sequence, complete acceptance criteria, planned
verification, documentation and ADR impact, risks, assumptions, and remaining
gates.

Before Coder entry, explicit human approval must identify the applicable plan
or handoff and its base. Any separately protected decision must also have its
own approval. Plan existence, prior discussion, or an unblocked design does not
constitute approval.

### Coder implementation or remediation report

The Coder returns the standalone report required by `$vddai-code`, including:

- task, handoff, and approval identity;
- `COMPLETE` or `BLOCKED` status;
- base, head, merge base, branch or worktree, complete committed range, staged
  and unstaged changes, and relevant untracked files;
- implemented behavior, affected contracts, and every changed file;
- acceptance-criterion evidence and tests or checks;
- exact commands and outcomes, omissions, risks, and rollback considerations;
- migration, data, artifact, lineage, compatibility, documentation, and ADR
  effects; and
- the complete range and state proposed for independent review.

A remediation report additionally preserves every human-selected
`VDDAI-REV-*` finding ID and provides the required closure-check evidence. The
Coder does not mark a finding resolved or issue a review verdict.

### Immutable Reviewer report and re-review report

The Reviewer creates a new immutable report under `docs/reviews/` with its
review identity, task and contract sources, exact reviewed subject, verdict,
acceptance coverage, checks, residual risks, and ordered remediation handoff.
Every actionable finding has a stable `VDDAI-REV-*` ID, severity, status,
location, evidence, required action, and closure checks.

Re-review never edits the prior report. It creates a numbered report, cites the
prior report, preserves every prior finding ID, records each as `VERIFIED
RESOLVED`, `STILL OPEN`, or `ACCEPTED RISK`, and assigns new IDs only to newly
discovered findings.

### Remediation selection and approval

Reviewer `CHANGES REQUIRED` does not authorize changes by itself. A human must
identify the latest report and explicitly select stable finding IDs, or approve
all open findings, before the Coder enters remediation mode. The selection
preserves each finding's required action and closure checks. A remedy that
would expand scope or cross a protected decision boundary requires replanning
and the applicable approval.

### QA report

QA returns the sixteen-section task report required by `$vddai-qa`. It binds
the task, approved plan, implementation report, current eligible review or
re-review, exact reviewed subject, environment, acceptance matrix, risk
applicability, scenarios, commands, regression evidence, defects, referrals,
blocked areas, residual context, final repository state, and next owner.

QA identifiers are stable within their series:

- `QA-SCN-*` identifies executed scenarios;
- `QA-DEF-*` identifies observable behavioral failures; and
- `QA-REF-*` identifies concerns owned by Reviewer triage.

On retest, preserve prior `QA-DEF-*` identifiers and mark them `VERIFIED
RESOLVED` or `STILL FAILING`; assign new IDs only to new failures or referrals.

### Documentation report and delta

Documentation returns the twelve-section task report required by
`$vddai-documentation`. It records `COMPLETE` or `BLOCKED`; a complete run also
records exactly `UPDATED` or `NO_CHANGE`. It identifies the unchanged
QA-verified implementation, immutable audit-only evidence, its authorized
documentation-only delta, routing and completeness decisions, validation,
inconsistencies, final Git state, and the proposed subject for human review.

`NO_CHANGE` is an evidence-backed Documentation outcome, not permission to
skip Documentation. Every documentation category still receives an explicit
applicability decision and required validation still runs.

### Pull request, CI, and merge evidence

When a pull request or CI run exists and is applicable, evidence must identify
the exact PR, head commit or range, required checks, and actual outcomes. A
missing, skipped, stale, or unavailable check is reported as such; no role may
infer that CI passed. Creating or updating a PR and pushing a branch require
their own authorization when repository rules or the invoking task require it.

The final human merge decision identifies the complete current merge subject
and current evidence. Approval of an earlier commit, implementation-only range,
or stale report does not approve a later subject.

## Transitions and Backward Routing

| Current result | Eligibility or next action | Backward condition and owner |
|---|---|---|
| Planner handoff ready | Human reviews the plan | Rejected, incomplete, contradictory, or human-gated design returns to Planner; Coder remains blocked |
| Explicitly approved Planner handoff | Coder may perform the bounded implementation | Missing, ambiguous, stale, or blocked approval returns to Planner/human before editing |
| Coder `COMPLETE` | Independent Reviewer receives the exact implementation report and range | Coder `BLOCKED` routes to Planner/human for plan or authority conflicts, or the named repository/environment owner for an external-state blocker |
| Reviewer `PASS` | QA-eligible only while the reviewed subject remains current | Any relevant later change requires independent re-review |
| Reviewer `PASS WITH DOCUMENTED RISK` | QA-eligible only if every remaining risk was already human-accepted, is not a correctness defect, and cannot prevent any criterion or scenario from being verified | Otherwise QA returns `BLOCKED` to Reviewer/human; QA does not accept the risk |
| Reviewer `CHANGES REQUIRED` | QA is ineligible | Human selects/approves open findings, then Coder remediates and Reviewer independently re-reviews |
| Re-review has `STILL OPEN` or new findings | Remediation loop repeats | Human selects/approves the next remediation set; no QA entry until an eligible current verdict exists |
| QA `PASS` | Documentation receives the current reviewed subject and QA report | Any relevant implementation change requires re-review and a new QA run |
| QA `FAIL` | Reviewer and human triage stable `QA-DEF-*` evidence | Approved remediation goes to Coder, then independent re-review, then QA retest against the new reviewed subject |
| QA `BLOCKED` | Route to the exact responsible owner and resume only when the stated entry condition is restored | Do not treat the blocker as code failure or authorize remediation without triage and human approval |
| Documentation `COMPLETE/UPDATED` or `COMPLETE/NO_CHANGE` | Human evaluates the complete proposed merge subject | Documentation completion is not merge approval |
| Documentation `BLOCKED` | Route to the responsible upstream role or human | Do not document around missing evidence, stale implementation, authority conflicts, failed validation, or an unauthorized write |
| Human merge decision | Merge only when explicitly authorized for the exact current subject | Rejection or requested change returns to the owning role; implementation changes restart review and QA as required |

## QA Blocker Routing

QA `BLOCKED` identifies the exact deficiency, affected criteria or scenarios,
risk, next owner, and resume condition:

| Blocker | Responsible owner |
|---|---|
| Missing, contradictory, or ambiguous task, acceptance criterion, approved design, or protected decision | Planner and human approver |
| Missing, incomplete, or inconsistent Coder report or implementation identity | Coder |
| `CHANGES REQUIRED`, missing re-review, stale review, or a material `QA-REF-*` | Reviewer, with human triage when risk or remediation approval is involved |
| Implementation, test, migration, configuration, contract, or relevant documentation changed after review | Reviewer after Coder reconciles and reports the current subject |
| Required database, service, backend, fixture, test data, artifact identity, approved external dependency, or safe environment is unavailable | Named environment owner or human responsible for the resource |
| Production, shared, destructive, secret-bearing, or otherwise unsafe environment | Human/environment owner supplies an explicitly safe test environment; QA does not proceed |

Restoring an environment without changing the reviewed subject permits QA to
resume without unnecessary code remediation. Any implementation change first
requires an eligible independent re-review.

## Documentation Blocker Routing

| Blocker | Responsible owner and required route |
|---|---|
| Missing or stale approved task, plan, or approval | Planner and human approver |
| Stale implementation or inconsistent Coder identity | Coder reconciliation, independent re-review, and a new QA run |
| Ineligible or stale Reviewer evidence | Reviewer or re-review |
| QA `FAIL`, QA `BLOCKED`, missing QA, or QA for a different subject | QA or the full upstream remediation/re-review/QA route |
| Executable-contract or ADR conflict, unapproved behavior, or scope ambiguity | Planner, human, and Reviewer as applicable; Documentation makes no architecture decision |
| Missing required Notion target or write authorization | Human; no inferred external write authority |
| Validation failure confined to Documentation's authorized delta | Documentation corrects only that delta and revalidates |
| Truthful documentation requires implementation, test, configuration, migration, or script changes | Human-approved Coder work, followed by independent re-review and QA |

## Evidence Freshness and Subject Identity

Every implementation-bearing handoff records base, head, merge base, branch or
worktree, committed range, staged and unstaged changes, and relevant untracked
files. Reports and approvals must identify which of those items they cover.

The immutable Reviewer report may appear as an identified audit-only file
without invalidating the implementation it reviewed. Other unexplained or
relevant changes are not silently absorbed.

After review, any production, test, migration, configuration, contract, or
relevant documentation change makes Reviewer evidence stale and requires
independent re-review. Raw Coder remediation evidence is never enough.

After QA, any change to the implementation-bearing subject requires both an
eligible re-review and a new QA run. Documentation first reconciles the exact
reviewed and QA-verified subject. After successful entry it may add only its
authorized documentation delta:

```text
QA-verified implementation range
  + immutable audit evidence
  + Documentation-owned documentation-only delta
  = proposed human merge subject
```

The Documentation delta is separately validated. It must not be represented
as part of the earlier Reviewer range or QA-tested behavior. A Documentation
change outside its approved write boundary invalidates the handoff and routes
back through the responsible upstream role.

## Mandatory and Optional Stages

Human approval gates never become optional because a change is small or low
risk. A stage may be omitted only when there is no artifact or behavior for
that role to own and the role's entry contract is genuinely inapplicable.

| Task class | Required lifecycle policy |
|---|---|
| Production or application behavior | Full standard lifecycle is mandatory, including task-specific tests, Reviewer, QA, Documentation, and human merge decision |
| Migration or persistence | Full lifecycle is mandatory; include Alembic upgrade, data preservation, practical downgrade, and representative database evidence as applicable; destructive behavior needs separate human approval |
| ML, data, model, or artifact | Full lifecycle is mandatory and `$vddai-ml-change` accompanies Planner/Coder; preserve split, preprocessing, lineage, compatibility, and promotion gates |
| Security or authentication | Full lifecycle is mandatory; changing security or authorization policy also requires explicit human approval and cannot be inferred from ordinary plan approval |
| Documentation-only or instruction-only repository change | Full lifecycle is mandatory; verification is documentation/contract-specific, and Documentation may return `NO_CHANGE` when the Coder-authored durable material is already complete |
| Remediation | Human selection/approval, Coder remediation, and independent re-review are mandatory; QA resumes only after a current eligible verdict |
| Planning-only task returned in the task conversation | Planner and human plan decision apply; Coder, Reviewer, QA, Documentation, and merge are omitted because no repository implementation subject exists |
| Planning artifact intended for the repository | Treat as a documentation-only repository change and use the full lifecycle |
| Review-only audit | Reviewer may act directly on an explicitly defined task, criteria, and range; if the objective ends with the immutable report, Coder, QA, and Documentation are omitted; any report merge still needs human approval, and later fixes need a valid approved Coder entry contract |
| Documentation `NO_CHANGE` | Documentation is still executed and validated; only the write delta is absent |
| Deployment or release after merge | Outside this lifecycle; requires a separate task, authority, verification, and production approval |

## Git, Human Control, and Protected Actions

- Use one independently reviewable task branch or worktree. Never push directly
  to `master`.
- Do not stage, commit, push, open or update a pull request, rewrite history, or
  merge unless the invoking request grants the corresponding authority.
- Keep commits logically focused and preserve unrelated user work.
- Never merge automatically. Implementation, review, QA, Documentation, and CI
  success are evidence for a human decision, not substitutes for it.
- A5 and this lifecycle end at the human merge gate. Merge completion does not
  authorize deployment or release.
- Separate explicit human approval remains required for production deployment,
  persistent-data or volume deletion, a destructive migration, security-policy
  changes, frozen ML evaluation changes, production model promotion or
  rollback, fundamental architecture changes, and real-secret mutation.

## Conceptual Lifecycle Scenarios

### A. Clean implementation

The human approves the Planner handoff. Coder returns `COMPLETE`; Reviewer
creates an immutable `PASS` report for the exact range; QA returns `PASS` for
the unchanged subject; Documentation returns `COMPLETE/UPDATED` or
`COMPLETE/NO_CHANGE`; the exact proposed subject waits for a human merge
decision.

### B. Reviewer failure

Reviewer returns `CHANGES REQUIRED`. QA is ineligible. A human selects the open
`VDDAI-REV-*` findings or approves all open findings. Coder remediates only that
scope and reports the new range. Reviewer writes a new immutable re-review.
Only an eligible current verdict permits QA.

### C. Repeated review failure

Re-review preserves prior finding IDs. A `STILL OPEN` finding or a new finding
keeps QA blocked. The human approves the next remediation set, Coder reports
the next delta, and Reviewer produces another numbered re-review. The loop
continues without rewriting prior evidence.

### D. QA behavioral defect

QA returns `FAIL` with stable `QA-DEF-*` evidence. Reviewer and the human triage
the behavior; Reviewer may create a `VDDAI-REV-*` finding. After explicit human
remediation approval, Coder changes the implementation, Reviewer independently
re-reviews it, and QA retests while preserving the original QA defect ID.

### E. QA blocked by environment

QA returns `BLOCKED` and names the unavailable or unsafe environment resource
and its owner. The environment owner or human restores a safe environment. If
the reviewed subject is unchanged, QA resumes without Coder remediation. If it
changed, independent re-review is required first.

### F. Stale evidence

An implementation change after review invalidates the review and requires
re-review. An implementation change after QA invalidates both readiness layers
and requires re-review plus a new QA run. Passing old commands or retaining an
old report does not restore freshness.

### G. Documentation-only delta after QA

Documentation reconciles and preserves the QA-verified implementation identity,
then owns only its authorized documentation delta. It validates that delta and
reports the combined proposed merge subject without claiming that the later
prose was reviewed or QA-tested.

### H. Human merge gate

Coder, Reviewer, QA, Documentation, and CI may all succeed, but no merge occurs
until a human explicitly approves the exact current merge subject.

### I. Low-risk non-implementation task

A planning-only question whose result remains in the task conversation ends
after Planner output and the human plan decision. There is no Coder, Reviewer,
QA, Documentation, or merge subject to process. This omission follows role
entry contracts and does not make a human gate optional. A repository artifact
would instead use the documentation-only full lifecycle.

### J. Production or deployment action

Human merge approval completes the development lifecycle only. It does not
authorize deployment, persistent-data deletion, a destructive migration,
secret mutation, or model promotion/rollback. Each requires a separately
authorized task and its applicable evidence and human gate.

## Related Sources

- [`AGENTS.md`](../../AGENTS.md)
- [`$vddai-plan`](../../.agents/skills/vddai-plan/SKILL.md)
- [`$vddai-code`](../../.agents/skills/vddai-code/SKILL.md)
- [`$vddai-review`](../../.agents/skills/vddai-review/SKILL.md)
- [`$vddai-qa`](../../.agents/skills/vddai-qa/SKILL.md)
- [`$vddai-documentation`](../../.agents/skills/vddai-documentation/SKILL.md)
- [`$vddai-ml-change`](../../.agents/skills/vddai-ml-change/SKILL.md)
- [`Documentation index`](../README.md)
