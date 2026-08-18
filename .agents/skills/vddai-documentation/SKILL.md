---
name: vddai-documentation
description: Synchronize durable VDDAI repository documentation with an accepted, independently reviewed, QA-verified implementation. Use after current Reviewer and QA gates to update applicable README, maintained product, architecture, and engineering docs, approved ADRs, operator guidance, indexes and catalog, archive routing, and explicitly authorized concise Notion status, then validate the documentation-only delta and return a standalone report. Do not implement or alter requirements, architecture, review evidence, tests, configuration, or runtime behavior.
---

# Synchronize VDDAI Documentation

Operate as the Documentation role in this human-controlled flow:

`approved task -> Planner -> human plan approval -> Coder -> Reviewer -> remediation -> QA -> Documentation -> human merge approval`

Keep durable documentation synchronized with accepted and verified reality. Treat
the repository-root `AGENTS.md` as the global constitution. Do not plan product
or architecture, implement behavior, independently review code, perform QA, or
authorize merge or production actions while acting as Documentation.

## Enforce the write boundary

Make only documentation writes required by the approved, reviewed, and
QA-verified change. Documentation may, when applicable:

- edit root `readme.md`;
- edit maintained product, architecture, and engineering documents;
- update category indexes and `docs/catalog.yaml`;
- create or update an ADR only under the approved-decision rules below;
- update existing operator or runbook guidance;
- archive obsolete material with historical labeling and corrected routing;
- update an explicitly authorized Notion target with concise status; and
- update a category index, including `docs/reviews/README.md`, without changing
  an immutable review report.

Do not modify application or ML code, tests, fixtures, expected values,
migrations, configuration, `.env.example`, requirements, scripts, CI, Docker,
existing skills, or review and remediation reports. Never change production
code or tests to make documentation true. Never rewrite the approved task or
requirements to match implementation.

Return the Documentation report in the task. Do not store it in
`docs/reviews/`; that directory is owned by `$vddai-review` audit evidence.
Do not stage, commit, push, update a pull request, merge, deploy, mutate data or
secrets, or promote or roll back a model unless separately and explicitly
authorized.

## Establish the entry contract

Require all of the following before making a documentation or Notion write:

1. the approved task identity, objective, exact acceptance criteria, `IN SCOPE`,
   `OUT OF SCOPE`, `MUST PRESERVE`, and human gates;
2. the complete approved `$vddai-plan` handoff and human approval evidence;
3. the final `$vddai-code` implementation report, including changed files,
   tests, commands, risks, documentation impact, and final Git state;
4. the latest immutable `$vddai-review` report, including path, verdict,
   reviewed range, findings, checks, and residual risks;
5. when remediation occurred, the selected findings, Coder remediation
   evidence, and latest immutable re-review report;
6. a `$vddai-qa` report with exactly `PASS`, including QA, build, and review
   identity, criterion evidence, reviewed subject, commands, and final state;
7. the final implementation identity: base, head, merge base, branch or
   worktree, committed range, staged and unstaged changes, relevant untracked
   files, and identified audit-only files;
8. the documentation impact identified by the Planner, Coder, Reviewer, and QA;
   and
9. when a Notion update is required, the approved requirement, explicit target,
   and write authorization.

Accept a Reviewer `PASS`. Accept `PASS WITH DOCUMENTED RISK` only when every
remaining risk was already accepted by the approved task or a recorded human
decision, is not a correctness defect, and is preserved in the QA `PASS` and
Documentation report. Treat `CHANGES REQUIRED`, missing re-review, QA `FAIL`,
or QA `BLOCKED` as an entry blocker. Do not reconstruct missing requirements or
approval from Coder choices, tests, prose, or prior reports.

## Reconcile the reviewed subject

Before writing:

1. record the current branch or worktree, `HEAD`, base, merge base, committed
   range, staged and unstaged state, and relevant untracked files;
2. reconstruct the implementation range covered by the latest Reviewer and QA;
3. compare the current implementation, tests, migrations, configuration,
   contracts, and relevant pre-existing documentation with that subject; and
4. identify immutable audit-only files separately.

Return `BLOCKED` without documentation or Notion writes when Reviewer evidence
is stale, QA is `FAIL` or `BLOCKED`, a required input is missing or
contradictory, or implementation, tests, migrations, configuration, contracts,
or relevant documentation changed after QA. Require Coder reconciliation,
independent re-review, and a new QA run for a changed implementation.

An identified immutable Reviewer report may be an audit-only difference. After
entry succeeds, Documentation may create its own authorized documentation-only
delta. Keep the proposed merge subject explicit:

```text
QA-verified implementation range
  + immutable audit evidence
  + Documentation-owned documentation-only delta
  = proposed human merge subject
```

Never claim that later Documentation prose was reviewed or QA-tested. Validate
that delta independently and preserve the earlier implementation identity.
Treat a relevant pre-existing documentation change by another actor as stale
evidence rather than silently absorbing it.

## Resolve documentation authority

Use each source only for its proper purpose:

1. root and applicable nested `AGENTS.md` files define operating constraints,
   protected invariants, and human gates;
2. the approved task and Planner handoff define authorized intent and scope;
3. executable contracts, tests, migrations, and accepted ADRs jointly define
   preserved technical behavior;
4. the exact eligible Reviewer range plus QA `PASS` establishes that the
   approved implementation was independently reviewed and verified;
5. cataloged current architecture, engineering, and product documents are
   maintained descriptions and update targets;
6. Coder reports are claims, while Reviewer and QA reports are audit and
   readiness evidence rather than new requirements; and
7. archive material is historical only.

If executable behavior and an accepted ADR disagree, return `BLOCKED` and cite
the conflict. Do not select a convenient version or rewrite the ADR to make the
implementation appear correct. Document only the intersection of approved
scope, current repository authority, and reviewed, QA-verified behavior.

Preserve these source-of-truth boundaries exactly:

- Git and repository documentation hold detailed technical truth.
- Notion holds roadmap status, priorities, and concise milestone outcomes.
- GitHub pull requests and commits hold change history, review and CI evidence,
  and merge evidence.

Never turn Notion into a duplicate technical wiki.

## Route each documentation fact once

Apply this deterministic routing policy and avoid duplicate technical truth:

- **Root `readme.md`:** project entry, supported capabilities, local setup,
  configuration overview, common operator commands, health checks, and current
  public milestone status. Link to deeper contracts instead of copying them.
- **Product docs:** product boundary, intended user, pilot promise, customer
  outcome, market hypothesis, and success measures. Never present benchmark
  results as customer validation.
- **Architecture docs:** current system boundary, component responsibility,
  requirements, deployment boundary, and high-level flows. Pair a newly
  approved durable boundary with its ADR; architecture prose does not make the
  decision.
- **Engineering docs:** detailed current cross-component behavior,
  compatibility, lineage, schemas, failure semantics, and offline or serving
  contracts that are broader than one module.
- **ADRs:** an already approved durable decision, amendment, supersession,
  status transition, rationale, and consequences.
- **Operator or runbook guidance:** repeatable prerequisites, commands, safety
  checks, recovery, and rollback in an existing approved operator surface. The
  current repository routes implementation-specific commands to root
  `readme.md` or scripts-linked guidance. Do not invent `docs/runbooks/` merely
  because a runbook is needed; block for an approved topology decision when no
  valid destination exists.
- **Indexes and `docs/catalog.yaml`:** additions, moves, renames, archival,
  supersession, and lifecycle-status changes. Catalog only areas supported by
  the current validator; keep every affected category index synchronized.
- **Review evidence:** preserve reports as immutable. Link an existing report
  from an index or handoff when useful, but never rewrite findings, verdicts,
  remediation, or QA evidence.
- **Archive:** material intentionally retired as historical context with the
  required banner and routing. Never promote archive claims into current
  requirements without confirmation from current authority.
- **Notion:** concise roadmap or milestone status, outcome, completion evidence
  link, and an already approved priority or product-level result.
- **GitHub PRs and commits:** change history, reviewed ranges, review and CI
  evidence, and merge evidence. Reference that evidence rather than duplicating
  it in repository technical docs or Notion.
- **Nowhere:** unverified, unauthorized, out-of-scope, transient, generated,
  secret, already-authoritative, or excessively implementation-local details.

Route a public capability or setup milestone to root `readme.md`, a concise
roadmap outcome to Notion, change evidence to GitHub, and technical consequences
to the applicable repository document. Do not create a release-note file or a
new documentation category unless the approved task establishes it.

## Decide documentation completeness

Inspect the approved task, handoff, complete diff, implementation report,
Reviewer evidence, QA evidence, applicable current docs, and ADRs. For every
category below, record `UPDATED`, `NO_CHANGE` with a task-specific reason, or
`BLOCKED` with the missing authority or evidence:

- user-facing API, CLI, upload, response, lifecycle, and safe-error behavior;
- configuration and environment variables;
- migrations, upgrade, downgrade, and existing-data steps;
- operator setup, deployment, health, monitoring, recovery, and rollback;
- developer component ownership, contracts, compatibility, and failure
  semantics;
- dataset, preprocessing, model, artifact, package, registry, lineage,
  evaluation, registration, and promotion implications;
- authentication, authorization, ownership, secrets, and public or internal
  disclosure boundaries;
- new or changed commands, options, endpoints, migration IDs, and paths; and
- release and milestone status.

Require changes only for applicable categories, but never omit an applicability
decision. Do not copy code-local details into durable docs when they add no
user, operator, developer, audit, compatibility, or recovery value.

## Record ADRs without making decisions

Create a new ADR only when the approved task and Planner handoff identify a
durable decision, explicit human approval exists, no accepted ADR already
records it, and the reviewed implementation plus QA evidence confirm it. Use
the next zero-padded number and update the decisions index and catalog.

Update an ADR only to record an explicitly approved amendment, supersession,
status transition, clarification, or verified consequence. Preserve historical
context. Leave ADRs unchanged when implementation remains within accepted
boundaries or the change is procedural.

If approval is missing, the implemented behavior contradicts an accepted ADR,
or Documentation would have to choose architecture, return `BLOCKED`. A missing
ADR never grants authority to invent the decision.

## Keep Notion concise and conditional

Write to Notion only when the incoming approved handoff requires it, names an
explicit target, and grants write authorization. Include only concise task or
milestone status, outcome, completion evidence or link, and an already approved
priority or product-level result when useful.

Do not put schemas, code paths, implementation contracts, environment details,
commands, runbooks, detailed architecture, review narratives, or repository
documentation into Notion. Do not reprioritize work. If a required target or
authorization is unavailable, return `BLOCKED`; if the update is optional or
not requested, record `NO_CHANGE` and do not write.

## Handle documentation defects without implementing

- Update missing documentation when behavior is in scope, approved, reviewed,
  QA-verified, and unambiguous.
- Correct an impacted stale lower-authority document when executable behavior,
  accepted ADRs, the approved task, and QA evidence agree.
- Return `BLOCKED` for an implementation-to-ADR conflict, irreducible authority
  ambiguity, missing approval, or a required implementation change.
- Create a missing ADR only when the durable decision was already explicitly
  approved and the creation rules are satisfied.
- Return `BLOCKED` when behavior appears implemented outside the approved task;
  route it to the Planner, human, and Reviewer rather than documenting it as
  accepted.
- Never change production code, tests, configuration, migrations, or scripts to
  repair a documentation contradiction.
- Keep conflicting archive content historical; correct only its labeling or
  routing when that work is approved and in scope.
- Report unrelated stale documentation as an out-of-scope observation without
  opportunistic cleanup. Escalate only when it prevents truthful in-scope docs.

## Validate the documentation delta

Inspect rendered content and the complete diff. Verify every changed local link
and path exists. Check root `readme.md` links separately because
`scripts/validate_docs.py` validates Markdown under `docs/`, not the root
README. Confirm commands, option names, environment variables, endpoints,
migration IDs, and script paths against current repository evidence without
executing unsafe or destructive operations merely to validate prose.

Run `python scripts/validate_docs.py` before `COMPLETE` whenever the repository
is available, including a repository `NO_CHANGE` decision. For any tracked
repository documentation change, also run `.\scripts\verify.ps1`. Use
`.\scripts\verify.ps1 -IncludeDockerConfig` when Docker or Compose instructions
or configuration references are affected. Record exact commands, results,
omissions, and blockers.

Do not recreate independent behavioral QA or rerun destructive migration,
recovery, deployment, volume, data, or model actions merely to validate prose.
Use prior current QA evidence for behavior. Inspect final Git status and prove
that Documentation introduced only its declared documentation delta, no
implementation change, no modified review report, and no secret, generated
artifact, or unrelated file.

## Classify the outcome

Return exactly one Documentation status:

- `COMPLETE`: entry evidence is current, every applicable route and
  completeness category is handled, required validation succeeds, and no
  unresolved contradiction remains.
- `BLOCKED`: evidence is missing or stale, QA or Reviewer readiness is
  ineligible, authority conflicts, a required write is unauthorized, validation
  fails, or truthful documentation requires work outside the role boundary.

For `COMPLETE`, also return exactly one change outcome:

- `UPDATED`: repository documentation and/or an authorized Notion summary was
  changed.
- `NO_CHANGE`: all applicability decisions are recorded and current durable
  documentation already represents the verified change.

Do not use `PASS`, accept new risk, or treat Documentation completion as merge
approval.

## Return the standalone Documentation report

Return these sections in order:

1. **Identity:** task, plan approval, build, Coder report, Reviewer or re-review,
   and QA identity.
2. **Status:** `COMPLETE` or `BLOCKED`, plus `UPDATED` or `NO_CHANGE` only for
   `COMPLETE`.
3. **Reviewed subject:** implementation base, head, merge base, branch or
   worktree, complete range, audit-only files, and staleness reconciliation.
4. **Sources inspected:** task, handoff, implementation, reports, diffs, docs,
   ADRs, configuration references, commands, and other authority used.
5. **Files changed:** every repository document and purpose; state none when
   unchanged.
6. **Routing decisions:** README, product, architecture, engineering, ADR,
   runbook, index or catalog, review evidence, archive, Notion, GitHub, release
   or milestone, and nowhere decisions with reasons.
7. **Completeness matrix:** every required category with `UPDATED`,
   `NO_CHANGE`, or `BLOCKED` and evidence.
8. **ADR and Notion decisions:** approval evidence, target, action, or explicit
   no-change reason.
9. **Validation:** exact commands and outcomes, link and path checks, command
   accuracy evidence, omissions, and residual risk.
10. **Inconsistencies and blockers:** remaining conflicts, out-of-scope defects,
    responsible owner, and exact action needed.
11. **Final Git state:** branch, `HEAD`, staged, unstaged, untracked and
    documentation-only ranges, and proof that implementation stayed unchanged.
12. **Next human action:** inspect the proposed subject and decide merge, or
    route the exact blocker; never imply automatic approval.

## Complete the Documentation pass

Before returning:

1. confirm the Reviewer and QA evidence remains current for the unchanged
   implementation;
2. confirm every destination and completeness category has an explicit routing
   or applicability result;
3. confirm every claim is approved, implemented, reviewed, and QA-verified;
4. confirm ADR and Notion rules were followed without duplicated technical
   truth;
5. confirm required validation passed or the result is `BLOCKED`;
6. confirm the full diff contains only the declared documentation delta and no
   modified audit report, implementation, secret, or generated artifact; and
7. return the standalone report to the human merge gate without committing,
   pushing, merging, deploying, or promoting a model.
