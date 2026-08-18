# A3 QA/Test Agent Contract Review

- Review ID: `VDDAI-A3-QA-REVIEW-2026-08-18`
- Date: 2026-08-18
- Task: A3 — Define QA/Test agent contract
- Branch: `codex/feat/a3-qa-test-contract`
- Approved base: `824e7f0c62329a572c503e2150165d020275bd11`
- Head: `824e7f0c62329a572c503e2150165d020275bd11`
- Merge base with `master`: `824e7f0c62329a572c503e2150165d020275bd11`
- Reviewed state: exactly two untracked implementation files; no committed,
  staged, or tracked unstaged implementation changes
- Finding namespace reserved: `VDDAI-REV-001` onward; no finding ID was
  assigned because no actionable finding was identified
- Verdict: **PASS**

## Scope

This review covers the complete A3 implementation against the approved base:

- `.agents/skills/vddai-qa/SKILL.md`
  - SHA-256: `d1bc0d4a83b430e566566c94622b648cdc5d057b9d7602538a2fc690c9d6eaf3`
- `.agents/skills/vddai-qa/agents/openai.yaml`
  - SHA-256: `5cdbab0500c7a9fc84013db6107d0068e0f28dfd30e860657530d9a32da16eaa`

The implementation is instruction and metadata only. Existing skills,
application code, ML code, tests, migrations, configuration, maintained
documentation, ADRs, CI, Docker, runtime state, artifacts, and model state are
outside the implementation range and unchanged. This review report is required
audit evidence and is excluded from the A3 implementation range.

## Contract Sources

- The approved A3 task, Definition of Done, evidence requirement, scope, and
  design questions supplied by the human.
- The human-approved eleven-section `$vddai-plan` result and standalone Coder
  handoff.
- The explicit A3 implementation authorization, QA-REF clarification, and Git
  restrictions.
- The standalone `$vddai-code` implementation report.
- Repository-root `AGENTS.md` and the cross-repository behavioral constraints
  in `app/AGENTS.md` and `ml/AGENTS.md`.
- `docs/README.md`, `docs/catalog.yaml`, and `docs/reviews/README.md`.
- `.agents/skills/vddai-plan/SKILL.md`,
  `.agents/skills/vddai-code/SKILL.md`,
  `.agents/skills/vddai-review/SKILL.md`, and
  `.agents/skills/vddai-ml-change/SKILL.md` plus their metadata.
- `.github/ISSUE_TEMPLATE/agent-task.md`,
  `.github/pull_request_template.md`, and `scripts/verify.ps1`.
- The installed skill packaging and metadata rules used by the existing VDDAI
  skills.

## Verdict

**PASS**

The implementation satisfies A3 without expanding into A4, A5, W7D2,
runtime behavior, permanent QA utilities, orchestration, or existing-role
changes. The contract requires a current independently reviewed subject and
derives expectations from the approved task, Planner handoff, and repository
authority rather than Coder assumptions.

Entry behavior is explicit for `PASS`, `PASS WITH DOCUMENTED RISK`,
`CHANGES REQUIRED`, remediation, and implementation changes after review. QA,
Reviewer, and Coder responsibilities remain distinct. Tracked files stay
read-only during QA; only isolated disposable diagnostics are allowed.

Criterion-specific evidence, risk-based adversarial selection, exact
`PASS`/`FAIL`/`BLOCKED` semantics, separate QA identifier namespaces,
ambiguity escalation, safe environment constraints, remediation/re-review/
retest behavior, and the standalone sixteen-section output schema are all
complete. The W7D2-class guidance requires representative PostgreSQL behavior,
deterministic concurrency coordination, real process/transaction crash
boundaries, durable-state inspection, idempotency evidence, and adjacent
regression coverage without claiming those runtime guarantees already exist.

No actionable correctness, scope, workflow, security, persistence, ML,
compatibility, documentation, metadata, or portability defect was identified.

## Findings

No actionable findings were identified. No remediation is required.

### Task compliance and scope

- The skill folder contains exactly the two approved files.
- No existing skill, runtime file, permanent test, migration, document, ADR,
  CI file, Docker file, generated artifact, or orchestration dependency changed.
- The workflow remains Planner -> human approval -> Coder -> Reviewer ->
  remediation -> QA -> Documentation -> human merge approval.

### Entry, authority, and freshness

- `SKILL.md:30-50` requires the approved task and plan, human approval, Coder
  report, latest Reviewer report, applicable remediation/re-review, exact Git
  range/state, and environment inputs.
- `SKILL.md:43-50` defines eligible and blocked Reviewer verdict behavior.
- `SKILL.md:52-63` requires byte/range reconciliation and blocks later relevant
  implementation changes while permitting an identified audit-only report.
- `SKILL.md:65-76` separates approved behavior, preserved executable/ADR
  contracts, implementation claims, audit evidence, and historical material.

### Role separation and defect routing

- `SKILL.md:78-88` distinguishes Coder implementation, Reviewer diff and finding
  ownership, and QA behavioral execution.
- QA uses `QA-SCN-*`, `QA-DEF-*`, and `QA-REF-*`; it does not assign Reviewer
  severity or prescribe code fixes.
- A `QA-REF-*` blocks only when material to behavioral verification or trust in
  the reviewed subject. Minor unrelated static observations remain reportable
  without forcing `BLOCKED`, matching the explicit human clarification.
- Behavioral failures route through human/Reviewer classification, approved
  Coder remediation, independent re-review, and QA retest.

### Verification behavior and outcomes

- `SKILL.md:90-105` requires criterion-by-criterion sources, scenarios,
  expected/actual behavior, and evidence; a generic suite result is insufficient.
- `SKILL.md:107-124` covers success, invalid and boundary inputs, retry,
  duplicates, idempotency, concurrency, crash/restart, transactions, partial
  failures, lifecycle, authorization, migration, compatibility, regression,
  and ML integrity with task-specific applicability.
- `SKILL.md:155-165` defines exactly `PASS`, `FAIL`, and `BLOCKED` and prohibits
  a QA `PASS WITH RISK` verdict.
- `SKILL.md:167-186` defines stable evidence and escalation without making QA a
  competing Reviewer.

### W7D2 readiness and safety

- `SKILL.md:126-141` is reusable for retry, crash, idempotency, concurrency,
  transition, and recovery behavior while deriving expected outcomes from the
  future approved task and Planner handoff.
- PostgreSQL is required for PostgreSQL-specific locking claims; deterministic
  barriers replace sleep-only concurrency evidence; crash/restart claims cross
  real process or transaction boundaries.
- `SKILL.md:143-153` preserves test/dev database isolation, disposable downgrade
  state, Docker-volume safety, artifact and split integrity, real-secret
  protection, and the human production-promotion gate.

### Reporting and completion

- `SKILL.md:201-220` defines all sixteen required report sections in the
  approved order.
- `SKILL.md:222-233` prevents incomplete criteria, unclassified risk categories,
  unreported diagnostics, repository drift, or prohibited production/Git action
  from being silently omitted.
- Metadata is exact, portable, directly invokable, and contains no machine-
  specific path.

## Acceptance-Criteria Coverage

| Acceptance criterion | Implementation evidence | Independent verification evidence | Result |
| --- | --- | --- | --- |
| Repository-level QA/Test skill exists | Exact two-file `.agents/skills/vddai-qa/` implementation | File inventory, frontmatter/YAML assertions, and skill validator | Pass |
| QA focuses on edge cases, failure modes, lifecycle/state transitions, applicable concurrency, integration, and regression | `SKILL.md:90-141` | Independent semantic scenarios and risk-category assertions | Pass |
| QA verifies the approved task, criteria, Planner handoff, and current contracts rather than Coder assumptions | `SKILL.md:30-76` | Entry, authority, staleness, and criterion-evidence assertions | Pass |
| Contract defines evidence for PASS, FAIL, and BLOCKED | `SKILL.md:155-165` and report schema | Exact-classification scenario and output-schema assertions | Pass |
| Missing coverage, contradictory requirements, untestable criteria, and ambiguity are escalated | `SKILL.md:39`, `74-76`, `102-105`, and `184-186` | Missing/contradictory/untestable scenario assertions | Pass |
| QA cannot alter requirements/tests, fix defects, act as Coder, or duplicate Reviewer | `SKILL.md:14-28` and `78-88` | Read-only, temporary-diagnostics, role, and referral assertions | Pass |
| Contract is reusable for W7D2 retry, crash, idempotency, concurrency, transition, and recovery verification | `SKILL.md:126-141` | W7D2 scenario assertions for backend, coordination, process boundary, durable state, and recovery | Pass |
| QA-REF materiality clarification is preserved | `SKILL.md:87-88` | Independent behavioral-failure/referral scenario | Pass |
| Metadata is exact and portable | `agents/openai.yaml:1-4`; frontmatter at `SKILL.md:1-4` | Exact YAML, description-length, invocation, encoding, and path assertions | Pass |

## Checks Run

| Command or check | Outcome |
| --- | --- |
| Complete reads of the approved task, Planner handoff, implementation authorization, Coder report, and current repository authority | Passed; scope, criteria, decisions, and role boundaries established |
| `git branch --show-current`, `git rev-parse HEAD`, `git rev-parse master`, `git rev-parse origin/master`, and `git merge-base HEAD master` | All resolve to the approved base `824e7f0c62329a572c503e2150165d020275bd11` |
| `git diff --name-status master...HEAD`, `git diff --name-status`, and `git diff --cached --name-status` | No committed, tracked unstaged, or staged implementation changes |
| `git status --short --branch --untracked-files=all` | Exactly the two implementation files before this report write |
| Complete reads and new-file diff inspection for both implementation files | Passed; the full 233-line contract and four-line metadata were inspected |
| Installed `quick_validate.py .\.agents\skills\vddai-qa` | Passed: `Skill is valid!` |
| Independent Python/PyYAML file, frontmatter, metadata, line-count, UTF-8/LF, final-newline, whitespace, portability, section-order, and report-schema assertions | Passed |
| Ten independent semantic scenarios required by A3 | All ten passed |
| Scope scan for machine paths, placeholders, LangChain, CrewAI, A4, and A5 | Passed; zero matches |
| `git diff --check`, `git diff --cached --check`, and `git diff --no-index --check -- NUL <file>` for both implementation files | Passed; no whitespace errors |
| SHA-256 calculation for both implementation files | Recorded in Scope; stable reviewed identities established |
| `.\scripts\verify.ps1` | Passed; Python 3.14.3, pip 26.1.2, exact pins, `pip check`, docs validation, and 254 tests in 47.49 seconds |

## Checks Not Run

- Black was not run because the implementation is Markdown and YAML only;
  independent encoding, newline, trailing-whitespace, and Git whitespace checks
  passed.
- Alembic upgrade/downgrade was not run because A3 changes no persistence or
  migration behavior.
- Docker configuration and container tests were not run because A3 changes no
  Docker, Compose, service wiring, or runtime behavior.
- Hosted CI was not run because the implementation is uncommitted and unpushed.
- A live fresh-agent forward test of `$vddai-qa` was not run. The complete
  contract was independently validated against all ten approved scenarios;
  actual task execution remains a procedural-model dependency.
- A4/A5 report persistence or orchestration was not tested because those tasks
  are explicitly outside A3.

## Ordered Remediation Handoff

No open finding exists and no remediation handoff is required. Preserve the two
implementation files unchanged unless a later independent phase discovers new
evidence.

The next workflow step is an independent `$vddai-qa` run against this reviewed
subject when directed by a human. This `PASS` verdict does not authorize a
commit, push, pull request, merge, deployment, production mutation, persistent-
volume deletion, secret action, or model promotion/rollback.

## Residual Risks and Assumptions

- The approved plan and human approval are task-conversation evidence rather
  than a repository planning artifact; both were available and unambiguous.
- The local `origin/master` ref was not fetched during review. It matched the
  approved base, local `master`, `HEAD`, and merge base at review time.
- `$vddai-qa` is a procedural contract. Static and scenario checks establish
  that required rules are complete and internally consistent, while future
  outcomes still depend on the executing model following them.
- No live forward QA run was performed during this independent code-review
  phase. That is the next distinct workflow role, not part of Reviewer scope.
- Durable QA-report storage remains intentionally outside A3 and awaits any
  separately approved A4/A5 decision.
- No implementation file was modified during review. No commit, push, PR,
  merge, deployment, data mutation, secret operation, Docker-volume deletion,
  or model action occurred.
