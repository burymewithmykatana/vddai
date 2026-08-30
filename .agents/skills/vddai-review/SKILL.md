---
name: vddai-review
description: Independently review VDDAI repository changes and write durable, actionable review reports for agent remediation and re-review. Check task compliance, correctness, regressions, security and authorization, database and worker safety, ML leakage and lineage, artifact compatibility, tests, documentation, and scope. Use when reviewing a VDDAI diff, branch, pull request, implementation, migration, ML change, or release readiness. Do not use to implement fixes.
---

# Review VDDAI Changes

Perform an independent, evidence-based review and persist its result for asynchronous agent handoff. Do not implement fixes, commit, push, merge, promote models, or mutate data while using this skill.

Do not modify this skill or another skill from review observations. A review
finding or process-learning recommendation is evidence only; any skill change
requires a separate independently approved Planner-to-Coder lifecycle.

## Enforce the write boundary

The review report is the only permitted repository write.

- If the user supplies a report path, use it.
- Otherwise create `docs/reviews/YYYY-MM-DD-<task-slug>.md` from the repository root.
- Create `docs/reviews/` when it does not exist.
- Never overwrite a report. Add `-r2`, `-r3`, and so on for subsequent reviews.
- Do not modify implementation, tests, configuration, migrations, instructions, documentation outside the report, or another review report.
- Leave the report uncommitted unless the user separately authorizes a commit.

If the report cannot be written, return the complete report in the task, state the write blocker, and treat the review as incomplete. Do not issue `PASS` without a durable report.

## Establish the review contract

1. Read the task, specification, and acceptance criteria.
2. Read the repository-root `AGENTS.md` and every applicable nested `AGENTS.md`.
3. Read relevant architecture decision records and documentation when the change touches an established contract.
4. Establish the complete review range. Include committed changes, staged and unstaged changes, and relevant untracked files unless the user explicitly limits the scope.
5. Map each acceptance criterion to implementation evidence and verification evidence.
6. Assign a review ID and reserve stable finding IDs in the form `VDDAI-REV-001`, `VDDAI-REV-002`, and so on.

If the intended base, task, or acceptance criteria cannot be determined from the repository or request, state the limitation. Do not invent requirements.

A freshness-validated local Graphify graph may optionally cross-check changed
component callers, dependents, and architecture impact. Treat it only as
derived structural discovery: it cannot replace review of the exact diff,
direct source, tests, configuration, migrations, or applicable contracts. If
it is unavailable, stale, incomplete, or conflicts with direct evidence,
report or disregard the limitation and continue the source-based review.

## Review in focused passes

### 1. Task compliance and scope

- Confirm the implementation addresses every acceptance criterion.
- Identify missing behavior, unnecessary changes, scope expansion, and accidental generated or artifact files.
- Check that public contracts and documentation are updated when behavior changes.

### 2. Correctness and failure behavior

- Trace normal paths, boundary conditions, invalid inputs, partial failures, retries, and recovery paths.
- Check backward compatibility and fail-closed behavior at production boundaries.
- Look for hidden coupling, stale assumptions, nondeterminism, and unsafe defaults.

### 3. API, authorization, and secrets

- Verify authentication and authorization at every affected boundary.
- Check input validation, error disclosure, logging, configuration handling, and secret exposure.
- Confirm new endpoints or operations preserve established response and failure contracts.

### 4. Database, migrations, and workers

- Review schema changes, migration ordering, downgrade behavior, constraints, indexes, and data compatibility.
- Check transaction boundaries, idempotency, locking, concurrency, retries, and crash recovery.
- Verify worker behavior cannot leave partially committed or ambiguously owned work.

### 5. ML integrity and production lineage

- Verify train, validation, and test isolation and look for direct or indirect leakage.
- Check preprocessing, feature extraction, feature dimensions, scoring, threshold selection, and evaluation consistency.
- Confirm artifact schemas, checksums, compatibility rules, model-package lineage, and fail-closed loading remain valid.
- Verify offline evaluation and online inference use compatible contracts.
- Treat model registration and production promotion as explicit human-controlled gates.

### 6. Tests, documentation, and diff hygiene

- Confirm tests cover changed behavior, failure cases, and contract boundaries rather than only implementation details.
- Run safe, read-only, applicable checks when feasible. Record exact commands and outcomes; never claim a check was run when it was not.
- Check documentation, examples, configuration templates, and operational guidance for drift.
- Inspect the final diff for unrelated edits, debug output, credentials, large binaries, and generated artifacts.

## Classify findings

Use these severities consistently:

- `BLOCKER`: unsafe to merge or release; can cause critical security, data, production, or ML-integrity failure.
- `HIGH`: material correctness or contract defect likely to affect users, production, or trustworthy evaluation.
- `MEDIUM`: real defect or meaningful maintainability risk with narrower impact.
- `LOW`: small issue worth fixing that does not materially threaten correctness.
- `NOTE`: non-blocking observation, question, or documented residual risk.

Do not inflate severity. Every actionable finding must include:

- a stable finding ID;
- severity and a concise title;
- status: `OPEN`, `ACCEPTED RISK`, `VERIFIED RESOLVED`, or `STILL OPEN`;
- exact file and tight line range when available;
- evidence and the failure scenario;
- why it matters to VDDAI;
- a concrete required action without implementing it;
- the verification required to close the finding.

## Write the durable report

Write the report before returning the review result. Use this structure:

1. title, review ID, date, task, scope, base and head or working-tree state;
2. contract sources and acceptance criteria reviewed;
3. verdict;
4. findings ordered by severity, with all required finding fields;
5. acceptance-criteria coverage mapped to implementation and evidence;
6. checks run with exact commands and outcomes;
7. checks not run and why;
8. ordered remediation handoff listing open finding IDs, dependencies, and closure checks;
9. residual risks and assumptions.

If there are no actionable findings, state that explicitly in the findings section. Still create the report.

The remediation handoff must be executable by another agent without access to this task's conversation. Include enough repository context to locate the problem, but do not prescribe unrelated refactors.

## Handle re-review

Treat the original report as immutable evidence. For re-review:

1. read the prior report and the remediation change set;
2. preserve every original finding ID;
3. mark each finding `VERIFIED RESOLVED`, `STILL OPEN`, or `ACCEPTED RISK` with fresh evidence;
4. assign new IDs only to newly discovered findings;
5. write a new numbered report rather than editing the prior report;
6. include the prior report path and a complete status summary.

## Return the result

Put findings first, ordered by severity, and include the report's repository-relative path.

Then report:

1. the ordered remediation handoff;
2. acceptance-criteria coverage;
3. checks run and their outcomes;
4. checks not run and why;
5. residual risks and assumptions;
6. exactly one verdict: `PASS`, `PASS WITH DOCUMENTED RISK`, or `CHANGES REQUIRED`.

Use `PASS` only when the reviewed scope satisfies the task and no material unresolved risk remains. Use `PASS WITH DOCUMENTED RISK` only when remaining risk is understood, explicitly accepted by the task contract, and not a correctness defect. Use `CHANGES REQUIRED` when any actionable defect or unmet acceptance criterion remains.

## Append process-learning evidence

After the required review report structure, append an unnumbered
`## Process-learning evidence` section with these fields:

- `Observation`: concrete process friction, a successful safeguard, an
  ambiguity, or `None observed`;
- `Evidence`: direct report IDs, finding IDs, commands, or repository paths;
- `Impact`: effect on correctness, handoff clarity, confidence, or rework;
- `Recurrence`: `first observed`, `repeated`, `unknown`, or `not applicable`;
- `Candidate improvement`: a proposal only, or `None`; and
- `Authority note`: state that the evidence does not authorize a skill or
  workflow change.

Keep the appendix inside the immutable report and include it in the returned
result. It does not create a finding, authorize remediation, or alter the
review verdict.
