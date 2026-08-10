## Summary

Describe the outcome and why this change is needed.

## Related Task

- Issue/task: ...
- Task objective: ...

## Scope

In scope:

- ...

Explicitly out of scope:

- ...

## Acceptance Criteria Mapping

| Acceptance criterion | Evidence |
|---|---|
| ... | Implementation/test/command reference |

## Changed Areas

- [ ] API, authentication, or authorization
- [ ] Database model or migration
- [ ] Worker, queue, or transaction lifecycle
- [ ] Dataset or manifest contract
- [ ] Preprocessing or feature extraction
- [ ] Scoring, threshold, or evaluation protocol
- [ ] Artifact schema, model package, or lineage
- [ ] Experiment tracking, registry, or promotion machinery
- [ ] Infrastructure, Docker, or CI
- [ ] Documentation or agent workflow only

Explain every checked area and its compatibility impact:

...

## ML Integrity

Complete when any ML, artifact, evaluation, registry, or serving boundary is
affected.

- [ ] Train, validation, and official-test roles remain isolated.
- [ ] Offline and online preprocessing remain compatible.
- [ ] Feature dimension, scorer direction, and threshold equality semantics are preserved or explicitly versioned.
- [ ] Dataset/model/artifact lineage and checksums remain complete.
- [ ] Invalidated artifacts and required regeneration are listed below.
- [ ] No official-test result was used for tuning or informal model selection.
- [ ] Registration does not imply production promotion.
- [ ] No production model was promoted or rolled back by this PR.
- [ ] Not applicable — explanation: ...

Invalidated or regenerated artifacts:

...

## Database and Data Safety

- [ ] No persistent schema or data change.
- [ ] Alembic migration included.
- [ ] Upgrade path tested.
- [ ] Downgrade path tested where practical.
- [ ] Existing-data behavior and data-loss risk documented below.

Migration/data notes:

...

## Verification Evidence

List only commands that were actually executed.

| Command | Result |
|---|---|
| `.\scripts\verify.ps1` | pass/fail/not run — details |
| Focused tests | pass/fail/not run — details |
| Migration checks | pass/fail/not applicable — details |
| Docker checks | pass/fail/not applicable — details |

If a check was not run, state the exact reason:

...

## Failure Paths and Security

Describe relevant failure handling, rollback behavior, authorization checks,
secret handling, and public/internal error boundaries.

...

## Risks and Rollback

- Residual risks: ...
- Known limitations: ...
- Application rollback plan: ...
- Data/artifact compatibility after rollback: ...

## Review Focus

Tell the independent reviewer where mistakes are most likely or most costly.

- ...

## Author Checklist

- [ ] The diff is limited to the stated task.
- [ ] Existing repository patterns and ADRs were followed.
- [ ] Behavior changes include regression tests.
- [ ] Public behavior and architecture documentation are current.
- [ ] No secrets, local datasets, generated binaries, or unrelated artifacts are included.
- [ ] No destructive migration, production deployment, security-policy change, or model promotion was performed without human approval.
- [ ] Remaining risks and failed/unavailable checks are reported accurately.
- [ ] This PR is review-ready but is not assumed approved for merge.
