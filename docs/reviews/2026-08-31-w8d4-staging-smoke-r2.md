# W8D4 Staging Smoke Re-review

- Review ID: `W8D4-REV-2026-08-31-002`
- Date: 2026-08-31
- Task: W8D4 — Add deployment smoke test and rollback
- Branch: `codex/w8d4-smoke-rollback`
- Base, HEAD, and merge base: `1b9f6160883361bdb99298b256815197ccab8eba`
- Subject: complete uncommitted W8D4 working tree: new staging client and tests,
  modified production-readiness operator guide, and prior immutable review.
- Prior report: [initial review](2026-08-31-w8d4-staging-smoke.md).
- Reviewer role: independent inspection; no implementation, test, deployment,
  registry, backup, or documentation writes other than this new report.

## Contract sources and acceptance criteria

Reviewed the human-approved eleven-section Planner handoff, subsequent user
authorization to keep settings editable outside Git and inspect/create backups,
root and application `AGENTS.md`, documentation index/catalog, maintained agent
workflow, production-readiness guide, and ADRs 0007, 0008, 0010, 0011, 0012, and
0014. Direct source inspection covered the existing W7 inference probe,
`PredictionRead`, inference and registry contracts, package loader/resolver,
registry rollback interface, and the full new client/tests.

The task requires automated post-deploy health, authentication, upload, queue,
inference, persistence, and owner-read checks; a definition of previous
application/model rollback; one performed and documented rollback rehearsal;
tests, documentation, and a visible commit. The approved rehearsal is an
application rollback between distinct compatible application digests with
unchanged model selection. No live model transition is needed to satisfy that
rehearsal criterion. A production registry transition remains separately gated.

## Verdict

**CHANGES REQUIRED**. No material repository implementation defect was found
in this reviewed subject, but required live HTTPS staging and rollback evidence
is absent. This corrects the initial report's premature narrowed PASS: excluding
mandatory operational acceptance criteria does not make the complete W8D4 task
eligible for PASS. The original report remains unchanged audit evidence and had
no original finding IDs to carry forward.

## Findings

### VDDAI-REV-001 — Required live deployment and rollback evidence is missing

- Severity: HIGH.
- Status: OPEN.
- Location: `docs/engineering/production-readiness.md`, lines 311–317;
  task acceptance criterion, not an identified defect in those truthful lines.
- Evidence: the new guide explicitly says repository tests alone cannot close
  W8D4. The Coder handoff reports no configured staging host/FQDN and no distinct
  approved current/previous GHCR application digest pair. No live staging smoke
  JSON or application rollback rehearsal record was supplied for this review.
- Failure scenario: declaring the deployment gate complete based on simulated
  HTTP tests, local image execution, or backup restoration would leave the
  actual ingress, deployed artifact identity, and recovery path unverified.
- Impact: the pilot would lack the operational recovery evidence required by
  W8D4 and ADR 0014 despite a functioning smoke client.
- Required action: obtain or provision the explicitly authorized real staging
  target within ADR 0014, identify two distinct compatible approved application
  digests, verify target-specific backups and schema compatibility, then execute
  the supervised application-only sequence in the operator guide. If target
  provisioning requires a missing resource or authority, report that exact
  blocker; do not substitute local development or relax TLS/digest guards.
- Closure verification: retain baseline/failure/recovery smoke JSON, exact API
  and worker image identities, unchanged registry/package identity, recovery of
  queued work, and readback of an existing completed prediction. Independently
  re-review the evidence before QA/Documentation eligibility and task closure.

No other actionable code or contract defect was identified. Existing result
schemas and the W7 validator provide full lineage/lifecycle, finite numeric,
latency, threshold, equality, and package-consistency checks. The client adds
strict origin/environment preflight, ownership checks, exact persisted second
read/history comparison, and final selection validation. It neither changes
serving selection nor invokes direct database or inference substitutes.

## Acceptance-criteria coverage

| Criterion | Implementation and evidence | Status |
|---|---|---|
| Health/auth/upload/queue/inference/persistence/read smoke after deploy | New staging client and failure-path tests; static trace covers all boundaries | Repository implementation present; live evidence unmet |
| Define previous application and model rollback | Production-readiness guide: explicit digests, schema/backup checks, existing audited registry rollback callbacks, no automatic transition | Definition present; operator execution not verified |
| Perform and document one rollback rehearsal | Guide defines distinct-image failure and recovery sequence | Unmet; VDDAI-REV-001 |
| Automated gate and tested rollback procedure | CLI JSON verdict, exit status, bounded child execution, persistent test-data warning | Client tests available; actual recovery unproven |
| Tests, documentation, visible commit | New tests and scoped operator guidance are uncommitted | In progress; final lifecycle documentation and commit pending |

## Checks run

Reviewer personally executed:

- `git status --short`, `git diff --stat`, `git diff -- docs/engineering/production-readiness.md`:
  expected scoped files only; direct reads included both untracked Python files.
- `git diff --check`: passed with no whitespace errors.
- `git rev-parse HEAD`, `git branch --show-current`: subject identity above.
- `.\.venv\Scripts\python.exe scripts/smoke_staging.py --help`: passed; actual
  CLI exposes the documented inputs and explicit data acknowledgement.
- `.\.venv\Scripts\python.exe scripts/validate_docs.py`: passed, 25 canonical
  documents and 71 Markdown files before adding this review report.
- `Get-FileHash scripts/smoke_staging.py,app/tests/test_smoke_staging.py,docs/engineering/production-readiness.md,docs/reviews/2026-08-31-w8d4-staging-smoke.md -Algorithm SHA256`:
  captured the reviewed byte identities below.

Coder-reported supporting evidence, not personally rerun by Reviewer: 44
focused smoke tests passed; an earlier full subject passed 465 tests without
skips against disposable PostgreSQL 16. These counts do not establish live
staging evidence or replace exact final verification attached by Coder/QA.

| File | Reviewed SHA-256 |
|---|---|
| `scripts/smoke_staging.py` | `3be7f1da4463867c92534fe3e6dd6e51ac16e791cc8e4f583409b5367f4914a9` |
| `app/tests/test_smoke_staging.py` | `72fc5a43940ce720025afdf3e5ae7f9bd1672f4cb9cb30dcc09363ed094cf06a` |
| `docs/engineering/production-readiness.md` | `cb691826e3c57181d7057cc29ab01d4ba0c6d11136b37fc9e766bac9d1bd0d3e` |
| Initial immutable review | `7bfe6ffac60adcac2651c59a3fd4b08a016e64bf7deb4e111863b9c61b271df3` |

## Checks not run and why

Reviewer did not run pytest concurrently with Coder's strict/full gate because
the repository tests share mutable test resources. No deployment, real staging
HTTPS probe, or rollback was executed by Reviewer. No production registry write
or destructive operation was attempted. Graphify was not used; all conclusions
come from direct sources without relying on unvalidated generated intelligence.

External local configuration/backups are contextual Coder evidence, not part
of the reviewed Git delta. Coder reports cold PostgreSQL backup restoration
into an isolated volume retaining four completed predictions and restored
artifact loading/real inference. Reviewer did not reproduce those operations;
they are not an application rollback rehearsal.

## Ordered remediation handoff

1. Preserve this report and the initial report. Keep VDDAI-REV-001 OPEN and the
   task incomplete while the real target/digest prerequisites are absent.
2. Attach final verification commands/counts tied to the file hashes above;
   re-review any subsequent implementation change. Do not use earlier passing
   counts as proof for later source edits.
3. Resolve the exact staging target and two approved image identities without
   changing ADR 0014 or manufacturing a model rollback target. Use verified
   target-specific backups, then perform the documented supervised rehearsal.
4. Supply the closure evidence listed in VDDAI-REV-001 for independent review.
   Complete eligible QA and Documentation afterward, record the scoped commit,
   and retain the human merge/push boundaries.

## Residual risks and assumptions

The CLI retains users/images/predictions; an ambiguous timed-out POST may have
committed even if the parent has no prediction ID. The supervisor bounds CLI
execution and discards partial private child output; calling `smoke_staging`
directly does not provide the parent-process DNS deadline guarantee. HTTP health
does not expose application image provenance, so independent container identity
capture remains necessary. Same-host backup copies alone do not protect against
host loss. No user authorization to waive mandatory live criteria was inferred.

## Process-learning evidence

- Observation: the initial review narrowed its PASS scope while mandatory live
  acceptance evidence remained unavailable.
- Evidence: initial W8D4 review verdict/coverage and VDDAI-REV-001 in this report.
- Impact: an apparent passing review could incorrectly advance the lifecycle
  despite an unmet task criterion; this report restores explicit full coverage.
- Recurrence: unknown.
- Candidate improvement: consistently separate repository verification results
  from the complete task verdict in existing review acceptance tables.
- Authority note: this evidence does not authorize a skill or workflow change.
