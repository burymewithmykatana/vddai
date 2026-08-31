# W8D3 Staging Provisioning Re-review R5

- Review ID: `W8D3-REV-2026-08-31-R5`; date: 2026-08-31.
- Prior report: [R4](2026-08-31-w8d3-staging-provisioning-r4.md).
- Base / HEAD / merge base: `8113c89897c4bc446551f0ec7adf204bae3b8c38`.
- Branch: `feat/w8d3-staging-provisioning`.
- Subject: complete W8D3 working-tree delta, including relevant untracked files;
  no staged changes or implementation commit. Reviewer writes only this report.

## Contract sources and approval

The original task, eight acceptance outcomes, complete Planner handoff, human
approval, implementation report and initial remediation evidence are supplied at
`C:/Users/S.R.G/.codex/attachments/5e3c61dd-eb09-4941-a7bc-d8c6a760b648/pasted-text.txt`.
The current task contains the subsequent explicit additive-launcher amendment
approval and the instruction to fix, independently review, and repeat until
ready for QA. R4 records these sources and the standalone R3-remediation report.
Current Coder evidence below supplements that record for REV-005.

Authority remains root/application AGENTS, role skills, current docs index and
catalog, accepted ADRs 0007-0012 and amended 0014, and the approved task. R1-R4
are immutable audit evidence. Direct source review was used, not Graphify.
The independent review covered the complete W8D3 subject in R4 and now its
four-file remediation, confirming all other non-audit subject hashes unchanged.

Scope remains repository-owned single-host Linux Docker Compose staging with
one immutable API/worker image, internal dependencies, external configuration,
Caddy HTTPS, durable local volumes, read-only approved artifacts, safe health
interfaces, and recovery guidance. Live deployment, paid resources, DNS, real
credentials, model promotion, schema/worker/API/security-policy changes and
W8D4 smoke/rollback execution remain excluded.

## Verdict

**PASS**

No actionable findings remain in the reviewed repository configuration scope.
All five findings are verified resolved. This is readiness for independent QA,
not a QA result, merge authorization, or proof of a deployed staging environment.

## Finding status and closure evidence

| Finding | Severity | Status | Fresh evidence |
|---|---|---|---|
| `VDDAI-REV-001` | HIGH | VERIFIED RESOLVED | Generated API healthcheck retains `/health` and `/health/model`; worker/Caddy require API health. Focused checks pass. |
| `VDDAI-REV-002` | MEDIUM | VERIFIED RESOLVED | Fixed document and CLI project identity retained; actual Compose render overrides conflicting ambient project name. |
| `VDDAI-REV-003` | HIGH | VERIFIED RESOLVED | Literal/allowlisted env validation rejects quote/interpolation/default/template/duplicate cases; actual render preserves accepted JWT and shared database values. |
| `VDDAI-REV-004` | MEDIUM | VERIFIED RESOLVED | Matching canonical internal URL rejects query routing, alternate targets, credential mismatch and PG* overrides; actual driver arguments retain `postgres:5432`. |
| `VDDAI-REV-005` | MEDIUM | VERIFIED RESOLVED | `validate_staging_settings` now restricts PostgreSQL password to `[A-Za-z0-9._~-]+`; six incompatible password cases fail before Compose. Accepted password survives actual Compose rendering, Alembic Config set/get and driver argument construction. |

REV-005 changes are confined to launcher, tests, env template and operator
guidance. The template/runbook require a long random supported literal password
and prohibit percent encoding. No Alembic implementation change was made.
Existing startup semantics and prior protections remain intact.

## Acceptance-criteria coverage

| Approved outcome | Implementation / verification evidence | Result |
|---|---|---|
| Reproducible provisioning/configuration | Versioned launcher/template, fixed project, explicit digests; accepted configuration traverses Compose/Alembic/driver checks. | Satisfied |
| API/worker use approved immutable image identity | Same validated digest, separate commands, no source mount/build substitution; immutable/container regression tests. | Satisfied |
| Configuration/secrets outside source control | External-file restriction, safe template, strict literal validation and non-disclosing errors. | Satisfied |
| Durable dependencies handled appropriately | Internal PostgreSQL/Redis, matching DSN, stable named volumes, shared uploads and read-only artifact snapshot. | Satisfied |
| HTTPS/stable endpoint planned | Validated FQDN, Caddyfile, only 80/443 published, documented operator prerequisites. | Satisfied as planned configuration |
| Authenticated behavior/health verifiable | Existing routes preserved, model-readiness dependency and literal JWT delivery verified. | Satisfied as interfaces; live exercise belongs to W8D4 |
| Deployment/rollback/recovery documented | Worker-stop, backups, artifact retention and downgrade constraints; corrected supported credential syntax. | Satisfied |
| No production deployment/model promotion | No external action, registry mutation, model generation or promotion added/performed. | Preserved |
| Approved additive-launcher amendment | ADRs 0012/0014 and index consistently permit staging invocation with W8D2 helper reuse. | Satisfied |

## Checks run

Independent Reviewer focused regression: **51 passed in 1.78 seconds**, exit 0.
This includes the real Docker Compose render and Alembic/driver handoff, using
only synthetic input and no database connection. Exact invocation:

```powershell
@'
import subprocess, sys, tempfile
with tempfile.TemporaryDirectory(prefix='vddai-r5-review-') as base:
    result = subprocess.run([sys.executable, '-m', 'pytest', '-q',
        '--basetemp=' + base, 'app/tests/test_run_staging_compose.py',
        'app/tests/test_run_immutable_compose.py',
        'app/tests/test_container_contract.py'])
print('Disposable reviewer pytest directory cleaned.')
raise SystemExit(result.returncode)
'@ | .\.venv\Scripts\python.exe -
```

The disposable directory was cleaned. Reviewer inspected the remediation,
template/runbook and complete-subject hash continuity with R4.

### Current standalone Coder evidence

Coder status: COMPLETE for approved REV-003/004/005 remediation, pending this
independent review. Only four subject files changed from R3/R4: launcher,
focused tests, env template and production-readiness guidance. Across both
iterations, 32 regression cases were added relative to the original 19-case
focused suite; the repository-env test now uses a disposable fake root.
No migrations, model artifacts, application runtime policy or W8D2 files changed.

Coder captured `powershell.exe -NoProfile -ExecutionPolicy Bypass -File
.\scripts\verify.ps1 -IncludeDockerConfig -IncludeFormatting` through the
pinned Python subprocess with `PYTEST_ADDOPTS=--basetemp=<unique OS-temp path>`
from `TemporaryDirectory(prefix='vddai-r5-gate-')`. Terminal result:
**exit 0; 416 passed, 7 skipped in 62.37 seconds**. Python 3.14.3/pip 26.2,
exact dependencies/pip check, changed Python formatting, documentation
(25 canonical / 69 Markdown before this report), Alembic single head
`20260821_04`, and Docker configuration all passed. Cleanup was confirmed.
Coder focused evidence was separately 51 passed in 2.21 seconds.
These are Coder results, distinct from the independent focused result above.

## Checks not run

- Reviewer did not duplicate the complete canonical gate. Its terminal result
  is available from the current Coder run; the old mixed-runner gap is resolved.
- No live services, image publication, external PostgreSQL connection,
  migrations against a database, DNS/TLS issuance, authentication/inference on
  deployed staging, rollback, or promotion. External PostgreSQL configuration
  was absent; seven optional tests remained skipped in the Coder gate.
- Independent QA has not run. Full deployment/W8D4 acceptance is not claimed.

## Ordered handoff to QA

1. No Coder remediation remains. QA should load the approved task/Planner and
   approval source named above, current conversation amendment/iteration
   approvals, original Coder reports, R4, this report and its current Coder
   evidence. These are available entry inputs; no approval is inferred from
   an audit report alone.
2. Confirm base/branch and compare all non-audit hashes below before verification.
   Evaluate all eight outcomes under the bounded configuration scope and
   independently obtain or classify required canonical evidence, including
   skipped integration coverage. Exercise malformed settings, readiness and
   fixed durable identity without treating config render as live deployment.
3. Return standalone QA evidence. Documentation follows accepted QA; human
   merge approval remains separate. Do not perform W8D4 probes, deployment,
   resource purchases, DNS/credential changes, data deletion or model actions.

## Residual risks and subject identity

Single-host/non-HA operation, manual backups, operator-provisioned approved
artifacts, GHCR access, host capacity and domain/TLS setup are explicit pilot
constraints. They are not unresolved correctness findings in this task.
The documented credential subset is intentionally narrower than general dotenv
or PostgreSQL URL syntax. Existing database volumes retain their own bootstrap
state; changing env values does not migrate existing credentials.

Unchanged tracked files are identified by the base commit. The following hashes
identify the exact reviewed non-audit delta; no implementation edits occurred
during review. Reports R1-R5 are separate immutable audit evidence.

| File | SHA-256 |
|---|---|
| `.gitignore` | `382f9240ede2be5b4f0d516441fe0482ad86ffed6afb8352a35fccd032f99aa2` |
| `app/tests/test_run_staging_compose.py` | `f131281963a8146b122e255b015d1786cdbdb5f76a9f5d9fe8b62b24b020faa0` |
| `deploy/staging/Caddyfile` | `8c3a9b18498a24326773a7eab992584d57ad3d773623e1848bb0435ee1879707` |
| `deploy/staging/staging.env.example` | `e64a293a11ab757d30ce50f4916e42f1744a87dc291ccfa250b4b28fdca71e24` |
| `docs/architecture/system-requirements.md` | `f70c6fb4381d14f859b62b64ac5bbeef787d5a1314705ddab6daaf75f0f36061` |
| `docs/catalog.yaml` | `81f1ce90eaaa8cdc06d78b52c92aa64a4ad5ac38403f0ec6f8695dd4014febb7` |
| `docs/decisions/0012-immutable-application-image-publication.md` | `d042a4efc9170057a01b91ab4529405d8a45ee669fe4c737d0478f1faf71db38` |
| `docs/decisions/0014-single-host-staging-environment.md` | `fb18d503c292ef7defc968689ed0ad33578302394d931d577edb9ef78bd66c94` |
| `docs/decisions/README.md` | `7747300a6e2ab1b51ee4091a18a185e9bb697240ee89fcfc5b54ed193181681b` |
| `docs/engineering/production-readiness.md` | `acb9bb292d0b07aa3027378f865aecaad90d03c443e1c373788863144f621d67` |
| `readme.md` | `72cb019196fb2c8ae4a7ac71ebf6614580e08cc188bcdaf1645768400b4dcf80` |
| `scripts/run_staging_compose.py` | `dbdfc49866e95d2dcaaa2bd7d2f6382537f44440e729dc558012b31b33e2f734` |

## Process-learning evidence

- Observation: testing the Compose-to-Alembic-to-driver configuration handoff
  closed the startup incompatibility while preserving migration implementation.
- Evidence: REV-005, `test_staging_literals_survive_real_compose_render`, six
  negative password cases, independent 51-pass and Coder 416-pass/7-skip results.
- Impact: review is ready for QA without a broader runtime change.
- Recurrence: repeated configuration-boundary lesson, now covered in regression.
- Candidate improvement: None beyond the implemented task-specific coverage.
- Authority note: this evidence does not authorize skill/workflow changes or
  expand deployment, model, merge or other human-controlled gates.
