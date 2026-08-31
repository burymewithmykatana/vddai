# W8D3 Staging Provisioning Re-review R3

- Review ID: `W8D3-REV-2026-08-31-R3`
- Date: 2026-08-31
- Task: W8D3 reproducible staging environment, including the human-approved
  additive-launcher contract amendment.
- Prior reports: [R1](2026-08-31-w8d3-staging-provisioning.md) and
  [R2](2026-08-31-w8d3-staging-provisioning-r2.md).
- Branch: `feat/w8d3-staging-provisioning`.
- Base / HEAD / merge base: `8113c89897c4bc446551f0ec7adf204bae3b8c38`.
- Scope: entire W8D3 working-tree delta, including unstaged and untracked
  implementation, tests, configuration, and documentation. No implementation
  commits or staged files. R1, R2, and this report are audit-only additions.
- Only this report was written during review. No implementation, secrets,
  external infrastructure, database, or model state was modified.

## Contract sources and approved scope

The user supplied the original eleven-section Planner handoff, the explicit
"approved, proceed" response, standalone Coder implementation evidence,
approval/remediation of VDDAI-REV-001 and VDDAI-REV-002, and R2 in the attachment
`C:/Users/S.R.G/.codex/attachments/5e3c61dd-eb09-4941-a7bc-d8c6a760b648/pasted-text.txt`.
The current task subsequently explicitly approved retaining the additive
staging launcher and reconciling the sole-entry-point wording. That approval
does not authorize deployment, secret issuance, model promotion, or merge.

Authority inspected: root and application AGENTS.md; docs index/catalog;
ADRs 0007-0012 and amended ADR 0014; production-readiness guidance; original
task/Planner and Coder reports supplied in this task; prior review reports.
Direct repository sources were used; no Graphify conclusion was relied upon.

Required outcomes remain:
1. reproducible provisioning/configuration;
2. API and worker run from the approved immutable image identity rather than
   mutable source state;
3. configuration and secrets remain outside source control;
4. durable dependencies are handled appropriately;
5. HTTPS and a stable staging endpoint are planned;
6. authenticated application behavior and health checks can be verified;
7. deployment and rollback/recovery implications are documented; and
8. no production deployment or model promotion occurs.

The approved amendment adds no runtime requirement: ADRs 0012 and 0014 must
consistently allow the staging launcher while preserving W8D2 behavior. W8D4
continues to own the live authenticated smoke test and rollback exercise.
Provisioning resources, DNS/TLS issuance, real credentials, multi-host storage,
new queue architecture, and model-selection changes remain excluded.

## Verdict

**CHANGES REQUIRED**

The additive-launcher documentation amendment correctly reconciles the earlier
contract contradiction. The canonical gate now has a captured successful Coder
result, so R2's missing terminal evidence is no longer the outstanding issue.
However, fresh safe diagnostics establish two configuration-validation defects
in the complete implementation subject. Existing green tests do not cover them.

## Findings ordered by severity

### VDDAI-REV-003 — HIGH — Raw env validation admits a default or empty effective JWT key

- Status: OPEN.
- Locations: `scripts/run_staging_compose.py:97`, `136-141`,
  `203-204`, and `230-231`.
- Evidence: `_parse_env_file` preserves quoting/interpolation syntax and
  `validate_staging_settings` checks that raw string. API and worker then
  receive the same file via Compose `env_file`, which interprets the syntax.
  In a real, render-only Docker Compose diagnostic, both
  `JWT_SECRET_KEY='change-this-secret'` and
  `JWT_SECRET_KEY=${VDDAI_REVIEW_UNSET_JWT}` passed staging validation.
  Compose rendered the former as the forbidden development key and the latter
  as an empty key when the variable was absent. Control input remained valid.
- Failure scenario: an operator uses ordinary dotenv quoting or an unresolved
  secret variable. The wrapper reports validation success but launches services
  with a known or empty signing key. `app/core/config.py` does not reject those
  values, and `app/core/security.py` uses the setting directly for HS256.
- Impact: the promised staging secret guard can be bypassed by configuration
  syntax; predictable signing material undermines JWT authentication.
- Required action: ensure validation and container delivery use the same
  effective values, or explicitly reject unsupported quoting/interpolation
  before Compose. Fail closed for effective empty, development, and template
  credentials. Do not print real values or change application security policy.
  Apply the consistent interpretation to shared PostgreSQL configuration too.
- Closure checks: permanent tests for the quoted development key, quoted
  template key, unresolved expansion, and valid synthetic literal configuration;
  invalid cases must stop before launch. A real render-only Compose check must
  show accepted values are delivered unchanged to API/worker and that
  PostgreSQL values are interpreted consistently. Run focused and canonical
  gates with synthetic inputs only.

### VDDAI-REV-004 — MEDIUM — DATABASE_URL substring validation allows an external effective host

- Status: OPEN.
- Location: `scripts/run_staging_compose.py:163-168`.
- Evidence: the validator accepts a URL containing `@postgres:` and the
  expected scheme without resolving connection options. With synthetic
  `postgresql+psycopg://review_user:review_password@postgres:5432/review_db?host=outside.example`,
  validation succeeds. SQLAlchemy's actual PostgreSQL/psycopg dialect produces
  connection arguments with `host == "outside.example"`.
  No database connection was opened during this diagnostic.
- Failure scenario: a copied DATABASE_URL retains a host query override. The
  launcher accepts it as internal even though application connections and
  startup Alembic migrations target another host.
- Impact: violates the approved internal-PostgreSQL deployment boundary and
  can separate application data/migrations from the named staging volume and
  its documented backup/recovery procedure.
- Required action: validate the effective database target using parsing
  consistent with the serving driver and fail closed on routing overrides,
  alternative hosts, or unsupported connection syntax that can leave the
  approved internal service. Keep errors non-disclosing; do not connect during
  validation.
- Closure checks: permanent regression proving the synthetic query-host
  override is rejected before Compose; positive coverage for the documented
  internal URL; malformed/alternate-host and routing-override coverage. Verify
  without opening an external connection; rerun focused and canonical gates.

### Prior finding status

- VDDAI-REV-001: VERIFIED RESOLVED for the reviewed readiness wiring.
  The current generated API healthcheck probes both `/health` and
  `/health/model`; worker and Caddy still require API `service_healthy`.
  Fresh focused tests pass. The existing model-health route returns 503 on
  unavailable selection. This does not claim a live deployed model test.
- VDDAI-REV-002: VERIFIED RESOLVED for ambient project naming.
  The generated document retains `name: vddai-staging`, and the invocation
  supplies `--project-name vddai-staging`. Fresh focused tests assert both.
  No live volumes were created or inspected.

## Acceptance-criteria coverage

| Criterion | Evidence | Result |
|---|---|---|
| Reproducible provisioning/configuration | Template, fixed project, immutable image checks exist; effective env/DSN interpretation is inconsistent. | Not satisfied: REV-003/004 |
| Immutable API/worker image | Shared validated digest, separate process commands, no source/build substitution. | Satisfied in review |
| External configuration/secrets | External env-file path enforcement remains; effective secret guard admits default/empty keys. | Incomplete: REV-003 |
| Durable dependencies | Named volumes and internal dependency services exist; accepted DSN can route elsewhere. | Not satisfied: REV-004 |
| HTTPS/stable endpoint planning | Caddy configuration, ports 80/443, explicit FQDN and operator prerequisites. | Satisfied in source review; live TLS excluded |
| Authenticated behavior/health verifiable | Readiness remediation retained; unsafe effective signing key remains possible. | Incomplete: REV-003 |
| Deployment/rollback/recovery documentation | Worker-stop, backups, artifact snapshot and downgrade constraints documented. | Satisfied as guidance; DSN defect undermines assumed target |
| No production deployment/model promotion | No production/model actions performed; no registry mutation introduced. | Preserved |
| Additive-launcher amendment | ADR 0012 cross-references ADR 0014; ADR 0014 explains validation reuse and independent invocation; index marks amendment. | Satisfied |

No application, API, worker, migration, ML pipeline, artifact, or security-policy
implementation changes are part of the documentation amendment.

## Checks run and reproducible evidence

- `git status --short --untracked-files=all`, `git rev-parse HEAD`,
  `git branch --show-current`, `git merge-base HEAD master`,
  `git diff --name-status`, `git ls-files --others --exclude-standard`,
  and direct complete-subject inspection established the range.
- `git diff --check`: passed.
- `.\.venv\Scripts\python.exe scripts/validate_docs.py`: passed before
  adding R3 (25 canonical documents, 67 Markdown files), and after adding R3
  (25 canonical documents, 68 Markdown files). Final subject SHA-256 comparison
  confirmed all non-audit files unchanged by review.
- Initial `.\.venv\Scripts\python.exe -m pytest -q
  app/tests/test_run_staging_compose.py app/tests/test_run_immutable_compose.py
  app/tests/test_container_contract.py`: 11 passed, 8 setup errors caused by
  WinError 5 on the default Windows pytest temp root. This was an environment
  failure, not passing staging evidence.
- Retried the same focused suite with an isolated OS temporary `--basetemp`:
  19 passed in 0.27 seconds, exit 0. Exact wrapper:

```powershell
@'
import subprocess
import sys
import tempfile
with tempfile.TemporaryDirectory(prefix='vddai-r3-pytest-') as base:
    result = subprocess.run([sys.executable, '-m', 'pytest', '-q',
        '--basetemp=' + base,
        'app/tests/test_run_staging_compose.py',
        'app/tests/test_run_immutable_compose.py',
        'app/tests/test_container_contract.py'])
print('Disposable pytest directory cleaned.')
raise SystemExit(result.returncode)
'@ | .\.venv\Scripts\python.exe -
```

The existing repository-local staging.env test target was confirmed absent
before running the focused tests; no real env file was overwritten.

The following reproduces the two executed read-only diagnostics. Run from the
repository root using `.\.venv\Scripts\python.exe -` with this script on
standard input. It creates only a synthetic OS-temp env file, captures Compose
output without displaying configuration/secrets, and opens no database
connection or Docker service. All three JWT cases were actually executed.
The DSN case was executed separately using the same statements.

```python
import json
import os
import subprocess
import tempfile
from pathlib import Path
from sqlalchemy.engine import make_url
from sqlalchemy.dialects.postgresql.psycopg import PGDialect_psycopg
from scripts import run_staging_compose as staging

source = Path("deploy/staging/staging.env.example").read_text()
for old, new in {
    "replace-staging-postgres-user": "review_user",
    "replace-staging-postgres-password": "review_password",
    "replace-staging-postgres-db": "review_db",
}.items():
    source = source.replace(old, new)
with tempfile.TemporaryDirectory(prefix="vddai-r3-review-") as temporary:
    env_file = Path(temporary) / "staging.env"
    for case, jwt in [
        ("control", "review-synthetic-secret"),
        ("quoted_default", "'change-this-secret'"),
        ("unset_expansion", "${VDDAI_REVIEW_UNSET_JWT}"),
    ]:
        env_file.write_text(source.replace(
            "replace-with-a-unique-high-entropy-staging-secret", jwt),
            encoding="utf-8")
        values = staging._parse_env_file(env_file)
        staging.validate_staging_settings(values)
        document = staging.staging_compose_document(
            application_image="ghcr.io/example/app@sha256:" + "a" * 64,
            artifacts_path=Path(temporary).as_posix(),
            environment_file=env_file, fqdn="staging.example.com",
            settings=values, postgres_image="postgres@sha256:" + "b" * 64,
            redis_image="redis@sha256:" + "c" * 64,
            caddy_image="caddy@sha256:" + "d" * 64)
        process_env = dict(os.environ)
        process_env.pop("VDDAI_REVIEW_UNSET_JWT", None)
        result = subprocess.run(
            ["docker", "compose", "--project-name", "vddai-staging",
             "-f", "-", "config", "--format", "json"],
            input=json.dumps(document), text=True, capture_output=True,
            env=process_env)
        assert result.returncode == 0, "Compose render failed; output withheld"
        key = json.loads(result.stdout)["services"]["api"]["environment"][
            "JWT_SECRET_KEY"]
        print(case, "accepted", "default:", key == "change-this-secret",
              "empty:", key == "")
    values["JWT_SECRET_KEY"] = "review-synthetic-secret"
    values["DATABASE_URL"] += "?host=outside.example"
    staging.validate_staging_settings(values)
    _, arguments = PGDialect_psycopg().create_connect_args(
        make_url(values["DATABASE_URL"]))
    print("External effective host accepted:",
          arguments["host"] == "outside.example")
```

Observed JWT results: control default=false/empty=false; quoted_default
default=true/empty=false; unset_expansion default=false/empty=true. Compose
returned 0 in each case. DSN effective-host comparison returned true.
Disposable synthetic-env and focused-pytest directories were cleaned by their
TemporaryDirectory contexts. No diagnostic script was retained in the repo.

## Checks not run

- The complete canonical gate was not repeated in this Reviewer phase.
  The preceding Coder phase in this same task captured
  `.\scripts\verify.ps1 -IncludeDockerConfig -IncludeFormatting` exiting 0,
  including 384 passed and 7 skipped in 69.56 seconds, dependency, formatting,
  Alembic graph, docs, and Compose configuration validation. That is recorded
  Coder evidence, not an independent QA PASS. R2's inability to retain a
  terminal result is therefore no longer the sole outstanding limitation.
- No live services, image pull/build/publication, DNS/TLS issuance,
  authenticated deployed probe, migration execution, rollback, or model
  promotion occurred. These require separately authorized environment work
  and/or belong to W8D4.
- No externally configured PostgreSQL was used. Driver connection-argument
  construction for REV-004 does not open a connection.

## Ordered remediation handoff

1. Human: select/approve VDDAI-REV-003 and VDDAI-REV-004 before Coder remediation.
   This review does not authorize fixes.
2. Coder: within the existing approved W8D3 architecture, remediate the staging
   configuration interpretation and database-target validation. Expected scope:
   `scripts/run_staging_compose.py`, its focused tests, and only necessary
   template/operator documentation of supported syntax. Preserve the approved
   additive-launcher amendment and resolved REV-001/002 behavior.
3. Do not change auth policy, application settings, public APIs, worker logic,
   schema, ML contracts, real credentials, infrastructure, or model selection.
   Return to Planner/human if a remedy requires a new boundary.
4. Execute each closure check above, focused regression, real synthetic Compose
   render, documentation validation, and the canonical gate with captured
   terminal status. Do not weaken tests or treat existing 19/384 green counts
   as proof of these newly demonstrated cases.
5. Reviewer: write R4 preserving all four IDs and verify the changed subject.
   QA remains ineligible until independent re-review restores readiness.
6. After eligible review, QA then Documentation precede the human merge gate.
   No commit, push, merge, deploy, DNS, credential, or model action is authorized.

## Residual risks, assumptions, and subject identity

Single-host local storage/registry and operator-owned backups remain approved
pilot limitations. External hosting capacity, GHCR access, DNS/TLS, and actual
deployment are not established by this review. No risk acceptance is inferred
for REV-003 or REV-004. The documentation-only amendment itself is coherent.

The following SHA-256 values identify the exact non-audit working-tree subject.
Future roles can compare bytes rather than inferring freshness from HEAD alone.
Unchanged tracked files are identified by the base commit.

| File | SHA-256 |
|---|---|
| `.gitignore` | `382f9240ede2be5b4f0d516441fe0482ad86ffed6afb8352a35fccd032f99aa2` |
| `app/tests/test_run_staging_compose.py` | `4687c5150a46e508565fb98888d728fc5601e76d693d6a2f1809009607b35dd4` |
| `deploy/staging/Caddyfile` | `8c3a9b18498a24326773a7eab992584d57ad3d773623e1848bb0435ee1879707` |
| `deploy/staging/staging.env.example` | `d429b37235e25bf12a035b63d98fed2a49979cb5cd991db43b8a03f589707fa1` |
| `docs/architecture/system-requirements.md` | `f70c6fb4381d14f859b62b64ac5bbeef787d5a1314705ddab6daaf75f0f36061` |
| `docs/catalog.yaml` | `81f1ce90eaaa8cdc06d78b52c92aa64a4ad5ac38403f0ec6f8695dd4014febb7` |
| `docs/decisions/0012-immutable-application-image-publication.md` | `d042a4efc9170057a01b91ab4529405d8a45ee669fe4c737d0478f1faf71db38` |
| `docs/decisions/0014-single-host-staging-environment.md` | `fb18d503c292ef7defc968689ed0ad33578302394d931d577edb9ef78bd66c94` |
| `docs/decisions/README.md` | `7747300a6e2ab1b51ee4091a18a185e9bb697240ee89fcfc5b54ed193181681b` |
| `docs/engineering/production-readiness.md` | `5ab3f9fe953dc6535e51157a2da0a460ea76e02e41a7efa90998272c650191d1` |
| `readme.md` | `72cb019196fb2c8ae4a7ac71ebf6614580e08cc188bcdaf1645768400b4dcf80` |
| `scripts/run_staging_compose.py` | `9208ac24e06d7f1bb7922efe4101f225719393b1b29f2f8fe5094c5872bbed5b` |

Final review state: seven modified tracked files; eight untracked files after
adding R3 (three audit reports and five implementation/configuration/docs
files); no staged changes or commits. All pre-existing subject hashes must
remain as above.

## Process-learning evidence

- Observation: raw-string configuration tests did not exercise Compose dotenv
  interpretation or PostgreSQL driver routing options; green regression counts
  therefore missed two boundary failures.
- Evidence: VDDAI-REV-003/004 diagnostics; fresh focused 19-pass result; prior
  canonical 384-pass/7-skip result.
- Impact: prevents mistaken readiness based solely on syntax checks and
  identifies narrowly reproducible remediation.
- Recurrence: first observed for these interpretation mismatches.
- Candidate improvement: test effective downstream configuration at the
  staging boundary with synthetic inputs (proposal only).
- Authority note: this evidence does not authorize a skill/workflow change,
  remediation, deployment, or a new approval.
