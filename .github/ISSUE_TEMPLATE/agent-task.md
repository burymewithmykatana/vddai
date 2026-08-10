---
name: Agent task
about: Define a scoped, testable VDDAI implementation task
title: "[TASK-ID] "
labels: ""
assignees: ""
---

# TASK-ID — Task name

## Objective

Describe one concrete outcome. State what will be true when the task is done.

## Context

Describe the relevant existing behavior, repository area, architecture decision,
and reason for the change. Link related issues or ADRs.

## In Scope

- ...

## Out of Scope

- ...

## Must Preserve

- Existing API or artifact compatibility: ...
- Security, ownership, or lifecycle behavior: ...
- Dataset, preprocessing, evaluation, or lineage invariant: ...

## Required Behavior

1. ...
2. ...
3. ...

## Acceptance Criteria

- [ ] Requested behavior is implemented.
- [ ] Required invariants remain true.
- [ ] Failure paths are safe and tested.
- [ ] No unrelated refactor or generated artifact is included.
- [ ] Applicable verification passes.

## Required Tests

- Regression test: ...
- Contract or integration test: ...
- Failure-path test: ...

## Required Documentation

- [ ] No documentation change is required; reason: ...
- [ ] Update `readme.md`: ...
- [ ] Add or update ADR: ...
- [ ] Document compatibility, migration, or artifact-regeneration impact: ...

## Data, Artifact, and Migration Impact

- Database migration required: yes/no — details: ...
- Existing data affected: yes/no — details: ...
- ML artifacts invalidated or regenerated: none/...
- Schema or contract version affected: none/...
- Required local-only inputs: none/...

## Verification

Canonical repository gate:

```powershell
.\scripts\verify.ps1
```

Additional task-specific checks:

```powershell
# Add focused tests, migration checks, or Docker checks here.
```

## Human Approval Gates

List any step that must stop for human approval, including destructive
migrations, security-policy changes, production deployment, or model promotion.

- ...

## Git Boundary

- Work in one task-specific branch or worktree.
- Keep the change independently reviewable.
- Do not push unless explicitly authorized.
- Do not merge automatically.

## Completion Report

The implementing agent must report:

- implementation summary;
- changed files;
- acceptance-criteria mapping;
- commands executed and their results;
- migration, compatibility, or regenerated-artifact impact;
- unresolved risks and known limitations;
- the final local diff status.
