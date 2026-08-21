# W7D3 Rate and Resource Guardrails Review

- Review ID: `VDDAI-W7D3-REVIEW-20260821-01`
- Date: 2026-08-21
- Task: W7D3 — Add rate limits and resource guardrails
- Verdict: `PASS WITH DOCUMENTED RISK`
- Base: `6f97a69372e325dd89ee46419a03d8878dc15a9d`
- Head: `6f97a69372e325dd89ee46419a03d8878dc15a9d`
- Branch: `codex/feat/w7d3-rate-resource-guardrails`
- Merge base: `6f97a69372e325dd89ee46419a03d8878dc15a9d`
- Review subject: the complete unstaged W7D3 working tree, comprising 13
  modified tracked files and seven intended untracked files; no staged or
  committed implementation delta exists.

## Contract sources and acceptance criteria

The review used the approved W7D3 task and Planner/Coder handoff, the human plan
approval in the task conversation, repository-root `AGENTS.md`, `app/AGENTS.md`,
`docs/README.md`, `docs/catalog.yaml`, current system requirements, ADRs 0005,
0009, 0010, and proposed ADR 0011, plus the complete implementation, migration,
tests, configuration, and documentation delta.

The reviewed acceptance criteria were:

1. limit prediction upload/request frequency;
2. enforce the configured upload size resource-safely;
3. limit per-user outstanding prediction jobs;
4. protect the PostgreSQL-backed queue from global pressure;
5. return clear retryable errors;
6. preserve authentication, ownership, authorization, and disclosure rules;
7. test guardrails, boundaries, concurrency, and defaults;
8. document effective limits and configuration; and
9. retain one independently reviewable v0.1.0-scoped W7D3 change.

Graphify validation reported a stale HEAD and was excluded from review evidence.
All material conclusions were established from direct repository sources.

## Verdict

`PASS WITH DOCUMENTED RISK`

The implementation satisfies all approved W7D3 criteria and preserves the
successful prediction API, W7D2 lifecycle and attempt fencing, storage
abstraction, authentication and ownership rules, and frozen ML contracts. No
actionable correctness, security, migration, concurrency, scope, test, or
documentation finding remains.

The documented residual risk is the human-approved application boundary:
FastAPI/Starlette receives and spools multipart content before the route-level
bounded read and authenticated rate transaction execute. The implementation
correctly bounds application-memory reading to the configured maximum plus one
byte, but transport-body and temporary-spool limits remain deployment work.
This is explicitly excluded by the approved plan, documented in README and ADR
0011, and is not an implementation defect within W7D3.

## Findings

No actionable findings.

No `VDDAI-REV-*` identifiers are assigned because the reviewed subject has no
required remediation. The residual upload-spooling limitation is an approved,
documented scope boundary rather than an open finding.

## Acceptance-criteria coverage

| Criterion | Implementation evidence | Review and verification evidence |
|---|---|---|
| 1. Request frequency | `PredictionAdmissionService.consume_request_slot()` persists a fixed window per authenticated user and locks the user row | Boundary/reset service test, API `429` and `Retry-After` test, PostgreSQL same-user concurrency test |
| 2. Resource-safe upload size | `ImageStorageService.store()` uses the size hint and an authoritative `maximum + 1` read | Exact-boundary, limit-plus-one, absent-size, and reported-size storage tests |
| 3. Per-user outstanding jobs | Admission counts only the caller's `queued` and `processing` rows inside the locked transaction | State-matrix service test, API cleanup test, PostgreSQL simultaneous same-user admission test |
| 4. Global queue pressure | Singleton `prediction_admission_control` row serializes global count plus insert | Cross-user service/API coverage and PostgreSQL simultaneous global-admission test |
| 5. Retryable errors | Oversize `413`, user rate/capacity `429`, global capacity `503`, safe details, integer retry headers | Exact API status, body, header, cleanup, and disclosure assertions |
| 6. Security boundaries | Ownership derives from authenticated `User.id`; administrators have no creation exemption; global errors expose no occupancy | Existing authentication/ownership regressions plus new administrator and global-disclosure tests |
| 7. Tests | New service, API, storage, migration, and PostgreSQL concurrency suites | Canonical suite and focused permanent tests |
| 8. Documentation | `.env.example`, README, system requirements, ADR 0011, catalog, decision index, and corrected application instruction | Documentation validator passed and reviewed content matches executable behavior |
| 9. Reviewable W7D3 scope | One task branch and bounded 20-file implementation subject | Git status, base, merge base, untracked inventory, and complete diff inspection |

## Checks run

Reviewer checks:

```powershell
git status --short --branch
git rev-parse HEAD
git merge-base HEAD 6f97a69372e325dd89ee46419a03d8878dc15a9d
git diff --check
python scripts/graphify_repository.py validate
.\.venv\Scripts\python.exe -m black --check <all changed Python files>
.\.venv\Scripts\python.exe scripts/validate_docs.py
.\scripts\verify.ps1 -IncludeDockerConfig
```

Outcomes:

- base, head, and merge base matched the approved commit;
- no staged changes or unrelated untracked files were present;
- `git diff --check` passed, with line-ending conversion warnings only;
- Graphify validation reported stale derived evidence and was disregarded;
- all 13 changed Python files passed Black;
- documentation validation passed with 21 canonical documents and 47 Markdown
  files;
- pinned Python 3.14.3, pip 26.1.2, exact requirements, and `pip check` passed;
- canonical pytest completed with `313 passed, 5 skipped` in 64.11 seconds;
- Docker Compose configuration validation passed.

The Coder's recorded PostgreSQL evidence was also reconciled with the permanent
tests: five W7D2/W7D3 PostgreSQL concurrency tests passed, and a disposable
PostgreSQL database completed W7D3 upgrade, data-preserving downgrade, and
re-upgrade before being removed.

## Checks not run

- The Reviewer did not independently rerun the five PostgreSQL integration
  tests because `VDDAI_TEST_POSTGRES_DATABASE_URL` was intentionally absent
  after the Coder restored the database container to its prior stopped state.
  The canonical run reported these five tests as skipped. Exact Coder evidence
  and the permanent concurrency tests were inspected; independent QA should
  execute them against a disposable PostgreSQL 16 environment.
- A full API/worker Docker stack build and health probe was not run because
  Compose structure and deployment are out of scope; `docker compose config`
  passed.
- Repository-wide Black was not used as a verdict gate because the repository
  has documented pre-existing baseline drift. Every changed Python file passed.

## Ordered remediation handoff

No remediation is required. There are no open finding IDs or closure checks.

The unchanged implementation subject is eligible for independent QA under the
workflow rule for `PASS WITH DOCUMENTED RISK`: the sole residual risk was
explicitly included in and accepted with the approved plan, is not a correctness
defect, and does not prevent any criterion from being verified.

## Residual risks and assumptions

- Multipart receipt and temporary spooling precede route execution. Deployment
  body/temp-storage limits remain a separately scoped operational control.
- The singleton admission row intentionally serializes accepted count-plus-
  insert transactions. Upload validation and storage occur outside that lock.
- A worker terminal commit racing an admission count can cause a conservative
  rejection but cannot cause capacity overshoot.
- Stale `processing` work consumes capacity until ADR 0010 recovery, preserving
  fail-closed queue pressure behavior.
- The fixed-window and admission tables contain only internal guardrail state;
  downgrade discards that ephemeral state without altering predictions or
  W7D2 retry metadata.

Reviewer completion is not QA, deployment, merge, or release approval. The
subject still requires independent QA, Documentation, and explicit human merge
approval.
