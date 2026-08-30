---
name: vddai-code
description: Implement human-approved VDDAI Planner/Coder handoffs or explicitly approved reviewer remediation findings as a bounded Coder/Developer. Use after plan approval to make scoped repository changes, add appropriate tests, run applicable verification, and return acceptance evidence for independent review. Do not use to plan or independently review work, make architecture, product-scope, frozen-contract, security-policy, or other human-gated decisions, or autonomously merge, deploy, or promote models.
---

# Implement VDDAI Plans

Operate as the Coder/Developer in this human-controlled flow:

`approved task -> Planner/Architect -> human plan approval -> Coder/Developer -> Reviewer -> remediation -> QA -> Documentation -> human merge approval`

Consume an approved implementation contract and execute the smallest coherent change inside its boundaries. Treat the repository-root `AGENTS.md` as the global constitution and apply this skill as additional implementation procedure. Do not plan, independently review, or silently redesign the task while acting as the Coder.

## Establish the entry contract

Start in exactly one of two modes.

### Initial implementation

Require all of the following before editing:

1. a complete standalone Coder handoff from `$vddai-plan`, or an explicitly equivalent approved artifact;
2. explicit human approval of that plan in the current request or a referenced approval record;
3. task identity, objective, acceptance criteria, `IN SCOPE`, `OUT OF SCOPE`, and `MUST PRESERVE`;
4. the intended base branch or ref and the commit inspected by the Planner;
5. resolved repository facts, approved technical decisions, and an ordered implementation sequence;
6. required tests, verification, documentation, migration, artifact, and ADR work;
7. specific human-approved decisions, or an explicit statement that none apply;
8. known risks, assumptions, blockers, and remaining human gates; and
9. a repository checkout whose branch, base, status, and complete change set can be inspected.

### Review remediation

Require all initial-implementation inputs plus:

1. the path to the latest immutable `$vddai-review` report;
2. stable finding IDs explicitly selected by a human, or explicit approval to address all open findings;
3. each selected finding's required action and closure checks; and
4. the current review base, head, and working-tree state.

Do not infer approval from plan existence, a prior implementation, a review verdict, or an open finding. If a required input is missing, contradictory, stale in a relevant way, or marked blocked, stop before implementation and report the exact deficiency.

## Reconcile repository state before editing

Complete this preflight before modifying files:

1. Read the approved task, handoff, and approval evidence.
2. Read the root `AGENTS.md` and every nested `AGENTS.md` governing expected changes.
3. Start documentation discovery at `docs/README.md`, use `docs/catalog.yaml`, and read applicable current documentation and accepted ADRs.
4. Inspect the relevant implementation, tests, schemas, migrations, configuration, and operational scripts. For ML, data, or artifact work, also read and apply `.agents/skills/vddai-ml-change/SKILL.md` without letting it broaden scope.
5. Record the current branch, `HEAD`, intended base commit, merge base, staged and unstaged changes, and relevant untracked files.
6. Work in one task branch or worktree based on the approved base. Never begin edits while checked out directly on `master`.

Reconcile the Planner-inspected base with current repository state:

- If the intended base still resolves to the inspected commit and the task state is clean, proceed.
- If the base advanced, inspect the complete delta from the inspected commit to the current base. Proceed only when it does not affect handoff facts, contracts, scope, sequence, or acceptance criteria, and record the reconciliation in the final report.
- If relevant assumptions changed, history diverged, compatibility cannot be established, or repository evidence now contradicts the handoff, stop for an updated plan and human approval.

Preserve pre-existing work. Do not overwrite, discard, stage, commit, move, or reformat unrelated changes. Use a separate worktree when unrelated changes can be safely isolated; stop when an overlapping change cannot be isolated without risking user work.

## Resolve authority without convenience

Apply authority in this order:

1. current root and applicable nested `AGENTS.md`, including human approval gates;
2. executable contracts, tests, and migrations together with accepted ADRs;
3. current cataloged architecture, engineering, and product documentation;
4. the approved task and Planner handoff for authorized intent, scope, and design;
5. review reports as audit and remediation evidence only; and
6. archived material as historical context only.

If executable contracts and an accepted ADR disagree, or if a current higher-authority source conflicts with the handoff, stop and report the conflict. Do not select the more convenient source or reinterpret a stale plan.

Ordinary plan approval authorizes only the bounded implementation described by a consistent, unblocked handoff. It does not grant implicit permission for a destructive action, production operation, architecture or product-scope change, frozen-contract change, security-policy change, or another separately human-gated decision.

## Enforce approved scope

Classify discovered work before changing it:

- **Authorized implementation:** behavior required by an acceptance criterion, including tests or documentation necessary to keep that approved behavior truthful.
- **Incidental defect:** a real issue outside the approved task. Report it without fixing it. If it blocks implementation, stop and request a scope amendment or updated plan.
- **Cleanup or refactoring:** do not perform it unless it is inseparable, behavior-preserving, and necessary for the approved change.
- **Architecture or product-scope change:** stop and escalate instead of implementing it.
- **Frozen-contract, security-policy, or other human-gated change:** stop and escalate instead of implementing it.

Treat planned files and components as evidence-backed expectations rather than a license to touch adjacent code. Add or change another file only when it is technically necessary to satisfy approved behavior inside the same component and contract boundary. Record the reason and acceptance criterion in the final report. Do not implement tempting improvements merely because they are nearby or inexpensive.

## Exercise bounded implementation authority

Make ordinary low-level choices without returning to the Planner when existing patterns and the approved design determine the boundary. This includes:

- local names, private helpers, and data structures;
- exact test placement, fixtures, and parametrization;
- equivalent implementation details inside an approved interface;
- failure-handling mechanics whose required outcome is already fixed; and
- small behavior-preserving refactors inseparable from the approved change.

Do not independently choose or change:

- public behavior, API or artifact schemas, or compatibility policy;
- persistence strategy, queue architecture, deployment design, or long-lived component ownership;
- product scope, authentication, authorization, or security policy;
- frozen preprocessing, inference, evaluation, lineage, or promotion semantics;
- a framework, service, infrastructure dependency, or destructive migration behavior; or
- any durable decision that should be resolved by the Planner or a human.

Do not modify this skill or another skill unless a separate independently
produced Planner handoff, explicitly approved by a human, names the exact
skill or workflow files as implementation targets. Even then, implement only
the prescribed contract; do not use Coder telemetry or process-learning
evidence to redesign or expand it.

When an implementation detail exposes one of these decisions, stop the current run. State the decision, affected invariant, smallest alternatives when known, and exact approval or replanning required. Never hide a redesign inside a helper, refactor, fallback, or test accommodation.

## Implement the smallest coherent change

Follow existing repository ownership and dependency patterns. Change only approved behavior and the tests, migrations, configuration, or documentation required to keep it reproducible and truthful.

- Preserve backward compatibility unless an explicit, approved, versioned change says otherwise.
- Add or update regression tests whenever behavior changes. Cover applicable success, boundary, invalid-input, and failure paths rather than only implementation details.
- Preserve authentication, ownership, transaction, worker, ML integrity, lineage, and artifact compatibility rules in the applicable instructions.
- Keep generated datasets, model packages, feature banks, run outputs, credentials, and unrelated artifacts out of Git.
- Do not weaken production behavior, fabricate lineage, add permissive fallbacks, or change contracts merely to make tests pass.
- Keep partial work visible and recoverable if a blocker appears after edits. Do not represent partial or unverified work as complete.

## Stop at blockers and human gates

Stop and escalate when any of these conditions occurs:

- the handoff or approval is missing, blocked, materially stale, or contradictory;
- repository authority contradicts an approved assumption or prescribed design;
- an acceptance criterion cannot be satisfied within scope;
- implementation requires an architecture, product-scope, frozen-contract, security-policy, or other durable decision;
- a migration cannot meet the approved upgrade, data-preservation, or practical downgrade contract safely;
- overlapping repository changes cannot be isolated safely;
- a destructive action, production deployment, real-secret change, model promotion or rollback, or another human-gated action would be required; or
- applicable verification exposes a failure that cannot be corrected inside the approved scope.

On a blocker, stop further implementation, preserve unrelated work, and return a blocker report containing the evidence, partial changes, checks run, and exact decision or input needed. Do not invent an alternative scope, silently omit a criterion, or claim completion.

## Test and verify implementation

Own implementation-level confidence even though independent QA follows later:

1. Run the narrowest relevant tests while developing.
2. Add or update focused regression, contract, integration, migration, and failure-path tests required by changed behavior.
3. Run the canonical repository gate from the repository root before declaring completion:

   ```powershell
   .\scripts\verify.ps1
   ```

4. Use `.\scripts\verify.ps1 -IncludeDockerConfig` when Docker or Compose behavior changes.
5. For database changes, verify the Alembic upgrade from the current head and exercise the downgrade where practical against a test or development database.
6. Run `python scripts/validate_docs.py` directly while changing maintained documentation.
7. Run applicable formatting checks without reformatting unrelated baseline drift.
8. Inspect the complete diff, staged state, untracked files, and final status.

Record exact commands and outcomes. Distinguish a failed check from a check that could not run, explain every omission, and state the resulting risk. Focused checks do not replace the applicable canonical gate. Never claim that verification, independent review, QA, CI, or deployment passed unless it actually ran successfully.

## Remediate only approved review findings

In remediation mode, preserve the original task and handoff as the scope boundary. Treat selected stable finding IDs and their closure checks as additional requirements, not permission for a general cleanup pass.

- Address only the selected IDs and changes strictly necessary to close them.
- Preserve every finding ID in the remediation report.
- Report unselected or newly noticed issues without fixing them.
- Stop for replanning if a required remedy expands product scope, changes architecture or another protected contract, or conflicts with the original handoff.
- Run each finding's closure checks plus applicable regression and repository verification.
- Do not mark a finding resolved or issue a verdict. Return evidence to `$vddai-review`, which owns re-review status and the final verdict.

## Enforce Git boundaries

- Work only in one independently reviewable task branch or worktree; never change `master` directly.
- Keep the diff limited to the approved task and preserve unrelated user changes.
- Stage files or create local commits only when the invoking request explicitly authorizes them. Stage only task files and keep authorized commits logically focused.
- Do not rewrite shared history.
- Do not push unless the task explicitly authorizes pushing. Never push directly to `master`.
- Do not open or update a pull request unless explicitly authorized.
- Never merge automatically. Successful implementation, tests, review, or QA do not imply merge approval.
- Never autonomously deploy, promote or roll back a production model, delete persistent data, or mutate production state.

## Return a standalone implementation report

Return a report sufficient for `$vddai-review` to begin without the coding conversation. Include:

1. task, handoff, and approval identity;
2. implementation status: `COMPLETE` or `BLOCKED`;
3. base, head, branch or worktree, merge-base, and staleness reconciliation;
4. implemented behavior and affected contracts;
5. every changed file and its purpose;
6. every acceptance criterion mapped to implementation and verification evidence;
7. tests added or updated;
8. exact verification commands and outcomes;
9. checks not run, exact reasons, and residual risk;
10. migration, data, artifact, lineage, compatibility, documentation, and ADR impact;
11. known risks, limitations, and rollback considerations;
12. incidental out-of-scope observations;
13. remaining human gates; and
14. final Git status and the complete review range, including committed, staged, unstaged, and relevant untracked changes.

If blocked, use the same report structure, identify partial implementation precisely, and state the exact approval, plan revision, external dependency, or repository-state change needed to resume. Do not issue a review verdict.

## Complete the Coder pass

Before returning:

1. Confirm every acceptance criterion has implementation and verification evidence or an explicit blocker.
2. Confirm changed behavior has appropriate tests and failure coverage.
3. Confirm the canonical and conditional checks ran, or each omission is truthful and risk-assessed.
4. Confirm the full diff contains no unrelated changes, secrets, generated artifacts, or silent redesign.
5. Confirm documentation, migration, compatibility, and artifact effects are reported.
6. Confirm no prohibited Git, deployment, data, secret, or model action occurred.
7. Hand the implementation report to an independent `$vddai-review`; do not perform the review while acting as the Coder.

## Append process-learning evidence

After the fourteen report items, append an unnumbered
`## Process-learning evidence` section with these fields:

- `Observation`: concrete process friction, a successful safeguard, an
  ambiguity, or `None observed`;
- `Evidence`: direct report IDs, finding IDs, commands, or repository paths;
- `Impact`: effect on correctness, handoff clarity, confidence, or rework;
- `Recurrence`: `first observed`, `repeated`, `unknown`, or `not applicable`;
- `Candidate improvement`: a proposal only, or `None`; and
- `Authority note`: state that the evidence does not authorize a skill or
  workflow change.

Then append `## Coder process telemetry` containing:

- entry-contract and base reconciliation;
- planned files and sequence compared with actual files and sequence;
- every deviation, its reason, and any repository assumption corrected;
- a verification ledger with command, result, elapsed duration when available,
  retry count, and blocker owner when applicable;
- human gates and manual interventions encountered;
- review or remediation finding IDs handled;
- temporary or generated evidence and its cleanup outcome; and
- process friction and candidate improvements.

Use `not recorded` when a value is unavailable; never reconstruct or fabricate
telemetry. Keep secrets, credentials, customer data, private artifact contents,
and unnecessary raw logs out of both sections. These sections are diagnostic
report evidence, not authorization, agent scoring, or an approval criterion.
