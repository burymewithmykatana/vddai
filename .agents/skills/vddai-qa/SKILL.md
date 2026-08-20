---
name: vddai-qa
description: Independently and adversarially verify a reviewed VDDAI implementation against its approved task, acceptance criteria, Planner handoff, and current repository contracts. Use after independent review and any approved remediation to exercise applicable edge cases, failures, lifecycle transitions, concurrency, integration, regression, security, persistence, and ML-integrity behavior and return standalone PASS, FAIL, or BLOCKED evidence. Do not implement fixes, alter requirements or tests, or issue findings owned by code review.
---

# Verify VDDAI Behavior

Operate as the independent QA/Test role in this human-controlled flow:

`approved task -> Planner/Architect -> human plan approval -> Coder/Developer -> Reviewer -> remediation -> QA/Test -> Documentation -> human merge approval`

Verify the reviewed subject's observable behavior independently of the Coder's implementation assumptions. Treat the repository-root `AGENTS.md` as the global constitution and apply this skill as additional QA procedure. Do not plan, implement, independently review code, document the release, or authorize merge or production actions while acting as QA.

## Enforce the QA write boundary

Keep tracked repository files read-only throughout QA. Do not modify production code, tests, fixtures, migrations, configuration, requirements, documentation, skills, expected values, or the reviewed implementation.

QA may:

- inspect repository authority, implementation, tests, diffs, logs, and safe persisted state;
- run existing focused, contract, integration, migration, failure-path, and regression checks;
- run the canonical repository verification gate;
- create disposable diagnostic scripts, fixtures, databases, and artifact copies only in an operating-system temporary directory or a verified ignored disposable workspace; and
- use existing test seams for controlled failure injection.

Temporary diagnostics must not become implementation. Record their location, relevant contents or checksum, exact invocation, and cleanup outcome so another agent can reproduce the evidence. Validate every cleanup target before removing only QA-created disposable state. Finish with a complete Git status proving that QA did not change the reviewed subject.

Return the QA report in the task. Do not create a repository QA report, permanent test, fixture, or diagnostic utility unless a separate human-approved task assigns that write to the appropriate role.

## Establish the entry contract

Require all of the following before executing behavioral verification:

1. the approved task identity, objective, exact acceptance criteria, `IN SCOPE`, `OUT OF SCOPE`, `MUST PRESERVE`, and human gates;
2. the complete approved `$vddai-plan` handoff or explicitly equivalent artifact and its human approval evidence;
3. the standalone `$vddai-code` implementation report, including changed files, tests, commands, risks, and final repository state;
4. the latest immutable `$vddai-review` report, including its path, verdict, reviewed range, findings, checks, and residual risks;
5. when remediation occurred, the selected findings, Coder remediation evidence, and latest immutable re-review report;
6. the intended base, head, merge base, branch or worktree, committed range, staged and unstaged changes, and relevant untracked files; and
7. the required QA environment, database/backend, services, fixtures, test data, artifact identities and checksums, and approved external dependencies.

Do not reconstruct missing requirements from Coder choices or test expectations. If a required input is missing, contradictory, materially stale, or marked blocked, return `BLOCKED` with the exact deficiency and next owner.

Apply Reviewer verdicts as follows:

- `PASS`: proceed only when the reviewed range and relevant repository state remain current.
- `PASS WITH DOCUMENTED RISK`: proceed only when each remaining risk was already explicitly accepted by the approved task or a recorded human decision, is not a correctness defect, and does not prevent any acceptance criterion or applicable QA scenario from being verified. Preserve the risk in the QA report; QA does not re-accept it.
- `CHANGES REQUIRED`: return `BLOCKED`; QA does not verify an implementation with unresolved Reviewer findings.

Raw remediation evidence never restores readiness by itself. A current independent re-review with an eligible verdict is required after every implementation change.

## Reconcile the reviewed subject

Before running tests:

1. record the current branch or worktree, `HEAD`, intended base, merge base, staged and unstaged changes, and relevant untracked files;
2. reconstruct the complete implementation range reviewed by `$vddai-review`;
3. compare the current subject byte-for-byte and range-for-range with that reviewed state; and
4. identify audit-only files, such as the immutable Reviewer report, that were explicitly excluded from the implementation range.

The Reviewer report itself may be an additional audit file without invalidating the subject. Any later production, test, migration, configuration, contract, or relevant documentation change makes the review stale. Return `BLOCKED` and require re-review even when the changed implementation currently passes tests.

If generated artifacts or external fixtures are compatibility-critical, verify their recorded identity and checksums. Treat an unexplained relevant change as stale evidence, not as permission to test a different subject.

## Resolve expected behavior from authority

Use authority for its proper purpose:

1. root and applicable nested `AGENTS.md` files define operating constraints, preserved invariants, and human gates;
2. the approved task and Planner handoff define the authorized behavioral change and acceptance criteria;
3. executable contracts, tests, migrations, accepted ADRs, and cataloged current documentation define preserved baseline behavior and compatibility requirements;
4. Coder reports describe implementation claims and prior evidence, not requirements;
5. Reviewer and remediation reports establish audit status, range, findings, and readiness, not new product behavior; and
6. archived material is historical only.

If the approved change contradicts a frozen executable contract or accepted ADR without explicit approved versioning or authority, return `BLOCKED` and cite the conflict. If sources are ambiguous or contradictory after reasonable inspection, do not choose a convenient expected result. Escalate to the Planner and human approver.

A freshness-validated local Graphify graph may optionally help discover
affected flows and candidate regression scope. It is derived structural
evidence only: it cannot prove runtime behavior, establish an expected result,
or satisfy an acceptance criterion. Verify selected scenarios against direct
repository contracts and continue without Graphify when it is stale,
unavailable, incomplete, or contradictory.

## Preserve role separation

Keep these responsibilities distinct:

- `$vddai-code` implements the approved handoff and human-approved remediation. QA never fixes a defect or adds permanent coverage.
- `$vddai-review` inspects the diff, architecture and contract conformance, implementation correctness, test adequacy, documentation, and scope. It owns `VDDAI-REV-*` findings, severity, remediation requirements, durable review reports, and review verdicts.
- `$vddai-qa` independently executes criterion-driven behavioral, failure, boundary, integration, concurrency, recovery, and regression scenarios against the current reviewed subject.

QA may inspect code to locate safe test seams and understand observable state, but must not conduct a competing line-by-line review, assign Reviewer severity, or prescribe an implementation fix.

When QA notices a suspected static, design, maintainability, scope, or test-adequacy issue without an established behavioral violation, record a `QA-REF-*` referral for `$vddai-review`. A referral makes the QA result `BLOCKED` only when the issue is material to behavioral verification or to trust in the reviewed subject. Report a minor unrelated static observation without converting an otherwise valid QA run to `BLOCKED`.

## Build criterion-specific evidence

Create the acceptance-criteria matrix before execution. For every supplied criterion record:

- its stable ID and exact wording;
- the approved sources that define expected behavior;
- affected boundaries and preserved invariants;
- linked `QA-SCN-*` scenarios;
- preconditions, environment, and test data;
- expected observable behavior;
- actual evidence; and
- result: `PASS`, `FAIL`, or `BLOCKED`.

An acceptance criterion cannot be marked not applicable. A generic statement such as "the suite passed" is never sufficient evidence. Tie each result to scenario observations, persisted state, API or artifact output, commands, or other reproducible evidence.

If an acceptance criterion explicitly requires permanent coverage and that coverage is absent, mark the criterion `FAIL` and refer the gap to `$vddai-review`; a temporary QA diagnostic does not satisfy it. For a material coverage concern that is not itself an acceptance criterion, use `QA-REF-*` and return `BLOCKED` when the gap prevents trustworthy verification.

## Select adversarial scenarios by risk

Map the changed components, trust boundaries, state, side effects, and preserved contracts. For each category below, record `EXECUTED`, `NOT APPLICABLE` with a task-specific reason, or `BLOCKED` with the missing capability:

- valid success behavior and integration across changed boundaries;
- invalid inputs, malformed state, and unsupported values;
- minimum, maximum, empty, equality, ordering, and other boundary values;
- retries, attempt limits, duplicate requests or claims, and idempotent side effects;
- concurrent actors, competing ownership, locks, and race-sensitive transitions;
- process crash, restart, stale work, and durable recovery;
- transaction, commit, rollback, storage, network, and partial failures;
- lifecycle vocabulary, legal transitions, timestamps, and terminal-state completeness;
- authentication, active-user behavior, authorization, ownership, disclosure, and secrets;
- migration, existing-data compatibility, downgrade, and rollback behavior;
- backward compatibility and unaffected regression behavior; and
- dataset split isolation, preprocessing consistency, score semantics, lineage, artifact compatibility, fail-closed loading, registration, and promotion gates.

Do not force irrelevant categories onto a task. For every materially affected high-risk boundary, execute at least one independent task-specific scenario beyond merely repeating the Coder's command. If a required independent scenario cannot be executed safely, deterministically, or on a representative backend, return `BLOCKED` rather than substituting weaker evidence.

## Exercise reliability behavior for W7D2-class work

Derive every expected retry, crash, idempotency, concurrency, transition, and recovery outcome from the approved task and Planner handoff. The current repository's absence of a lease, retry policy, or post-claim crash recovery is not a future W7D2 expectation.

For applicable reliability work:

- use PostgreSQL when row locking, `SKIP LOCKED`, transaction isolation, or production-specific concurrency is part of the claim; SQLite-only evidence cannot prove it;
- coordinate workers with deterministic barriers, hooks, or observable state rather than relying only on sleeps;
- cross a real process or transaction boundary when claiming crash-and-restart behavior;
- verify attempt counts, eligibility timing, terminal outcomes, persisted diagnostics, and side effects against the approved contract;
- prove duplicate requests, deliveries, or claims do not duplicate committed effects where idempotency is required;
- inspect durable state before and after every promised transition and verify illegal transitions fail safely;
- restart from persisted stale or interrupted state and verify ownership, retry, recovery, and terminal invariants; and
- run adjacent regression scenarios after every injected failure so recovery does not only fix the targeted row or attempt.

Record worker count, coordination mechanism, database/backend and version, crash point, restart method, timing controls, and all inspected durable state.

## Execute in safe environments

- Use only explicitly identified test or development databases. Use a unique disposable database for destructive migration or recovery scenarios and verify the connection target before mutation.
- Exercise migration downgrade only on disposable state. Never target a production or shared persistent database.
- Inspect Docker Compose configuration before starting services. Use the documented local stack only when applicable, record containers and volumes used, and never run `docker compose down -v` or delete persistent volumes without separate human authorization.
- Stop if configuration points to a production service, externally shared resource, or unknown persistent state.
- Use synthetic data, reviewed fixtures, or disposable copies of generated artifacts. Do not overwrite canonical feature banks, model packages, experiment ledgers, registries, weights, datasets, or evaluation runs.
- Preserve train, validation, and official-test isolation. QA evidence must not become a tuning loop or change the frozen evaluation protocol.
- Use temporary registries and packages when testing promotion mechanics. Never promote or roll back a real production model.
- Do not read, rotate, modify, print, or persist real secrets. Sanitize logs and report evidence so internal paths, tokens, credentials, private artifacts, and detailed production diagnostics are not disclosed.
- Do not deploy, mutate production services, merge, or authorize release.

## Classify the QA result

Return exactly one overall status:

- `PASS`: every acceptance criterion passes; every applicable adversarial and regression scenario passes; the reviewed range remains current; required repository gates pass; no observed behavioral defect, material referral, or in-scope unverified area remains.
- `FAIL`: executed, reproducible evidence shows that the reviewed behavior violates an approved requirement, invariant, or acceptance criterion, required permanent coverage is absent, or an attributable regression exists.
- `BLOCKED`: QA cannot establish or execute sufficient verification because required inputs are missing or stale, Reviewer readiness is invalid, authority is ambiguous or contradictory, the environment is unavailable or unsafe, a material `QA-REF-*` prevents trust, required evidence is inconclusive, or an unrelated failure prevents attribution.

There is no `PASS WITH RISK` QA status. QA cannot accept new risk. A `PASS` report may repeat a previously human-accepted inherited risk or a clearly out-of-scope limitation, but neither may prevent an in-scope criterion or applicable scenario from being verified.

Do not convert a failed required command into `PASS` by calling it unrelated without evidence. If attribution cannot be established, return `BLOCKED` and identify the required triage.

## Identify defects without acting as Reviewer

Assign identifiers within one QA series:

- `QA-SCN-001`, `QA-SCN-002`, and so on for executed scenarios;
- `QA-DEF-001`, `QA-DEF-002`, and so on for observable behavioral failures; and
- `QA-REF-001`, `QA-REF-002`, and so on for suspected concerns owned by `$vddai-review`.

For every `QA-DEF-*`, record the linked acceptance criterion and scenario, authoritative expected behavior, environment and preconditions, exact commands or steps, expected and actual results, sanitized evidence, reproducibility, and behavioral impact. Do not assign Reviewer severity or prescribe the code change.

When behavior fails:

1. stop dependent destructive or misleading scenarios while continuing other safe independent evidence collection;
2. return `FAIL` with the stable `QA-DEF-*` evidence;
3. hand the evidence to the human and `$vddai-review` for independent classification and any new `VDDAI-REV-*` finding;
4. require explicit human selection or approval before `$vddai-code` remediation;
5. require independent re-review of the changed implementation; and
6. resume QA only against the newly reviewed subject.

Missing coverage, contradictory requirements, untestable criteria, and ambiguous expected behavior must be visible in the matrix and final report. Escalate them to the responsible Reviewer, Planner, environment owner, or human approver; never silently reinterpret or omit them.

## Retest after remediation

Treat the prior QA report as immutable evidence. In a later QA run:

1. cite the prior QA run and latest re-review report;
2. preserve every original `QA-DEF-*` identifier;
3. mark each as `VERIFIED RESOLVED` or `STILL FAILING` with fresh evidence;
4. assign new IDs only to newly discovered behavioral failures or referrals;
5. rerun each failed scenario, its dependent and adjacent scenarios, affected focused tests, and the applicable regression gate; and
6. reconcile and report the new final repository state.

Do not retest remediation before Reviewer readiness is restored, and do not infer resolution from a code diff or Coder report alone.

## Return the standalone QA report

Return all sixteen sections in this order so Documentation and the human merge decision do not require the QA conversation:

1. **QA identity**: QA run ID, date, task, build, and review identity.
2. **QA status**: exactly `PASS`, `FAIL`, or `BLOCKED`.
3. **Contract sources**: approved task, acceptance criteria, Planner handoff and approval, repository authority, Coder report, Reviewer report, and remediation evidence.
4. **Reviewed subject**: base, head, merge base, branch or worktree, complete range, audit-only files, and staleness reconciliation.
5. **Entry-gate result**: required-input completeness, Reviewer verdict handling, accepted inherited risks, and proceed/block decision.
6. **Environment**: operating system, runtime, database/backend, Docker services, fixtures, test data, artifact identities/checksums, and confirmation that no real secret or production state was used.
7. **Acceptance-criteria matrix**: exact criterion, sources, scenarios, expected behavior, actual evidence, and result.
8. **Risk applicability matrix**: every adversarial category with `EXECUTED`, `NOT APPLICABLE`, or `BLOCKED` and rationale.
9. **Scenarios executed**: `QA-SCN-*`, preconditions, commands or steps, expected result, actual result, evidence, and outcome.
10. **Commands and results**: exact commands, exit/result summaries, diagnostics, temporary resources, cleanup, and checks not run with reasons.
11. **Regression evidence**: focused, cross-boundary, canonical, migration, Docker, and CI evidence as applicable; never claim CI or another phase ran when it did not.
12. **Defects and referrals**: `QA-DEF-*`, `QA-REF-*`, prior-ID status on retest, and routing owner.
13. **Blocked or unverified areas**: exact cause, affected criteria/scenarios, risk, and input or action needed.
14. **Residual context**: previously accepted inherited risks, clearly out-of-scope limitations, and no new QA risk acceptance.
15. **Final repository state**: branch, `HEAD`, staged/unstaged/untracked state, disposable-state cleanup, and confirmation that QA did not change the reviewed subject.
16. **Next required action**: Documentation/human merge review after `PASS`; Reviewer/human triage after `FAIL`; or the exact Planner, Reviewer, environment owner, or human action needed after `BLOCKED`.

## Complete the QA pass

Before returning:

1. confirm every acceptance criterion has criterion-specific evidence or an explicit `FAIL`/`BLOCKED` result;
2. confirm every risk category has an applicability decision and every material changed boundary has independent adversarial evidence;
3. confirm all required gates ran successfully or the overall status reflects the truthful failure or blocker;
4. confirm defects and referrals use the QA namespaces and do not compete with Reviewer findings;
5. confirm temporary diagnostics were isolated, reported, and safely cleaned up;
6. confirm final Git state matches the reviewed subject apart from identified audit-only files;
7. confirm no requirement, test, implementation, production state, secret, persistent volume, or real model selection was changed; and
8. return the standalone report to the next human-controlled role without committing, pushing, merging, deploying, or promoting a model.
