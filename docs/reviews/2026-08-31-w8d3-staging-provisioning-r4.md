# W8D3 Staging Provisioning Re-review R4

- Review ID: `W8D3-REV-2026-08-31-R4`
- Date: 2026-08-31
- Task: W8D3 reproducible staging configuration; approved R3 remediation.
- Prior report: [R3](2026-08-31-w8d3-staging-provisioning-r3.md).
- Base / HEAD / merge base: `8113c89897c4bc446551f0ec7adf204bae3b8c38`.
- Branch: `feat/w8d3-staging-provisioning`.
- Subject: complete unstaged and untracked W8D3 delta, with no staged changes.
  This independent Reviewer changed only this new audit report.

## Contract sources and approval

Reviewed root and application AGENTS instructions, the review skill, docs
index/catalog and workflow contract, relevant ADRs 0007-0012 and amended 0014,
the staging implementation/tests/template/Caddyfile, changed maintained docs,
immutable launcher, Dockerfile, application settings/health, and Alembic startup.
Prior R1/R2/R3 are audit evidence, not requirements. Graphify was not used;
direct repository inspection establishes the findings.

The supplied attachment at
`C:/Users/S.R.G/.codex/attachments/5e3c61dd-eb09-4941-a7bc-d8c6a760b648/pasted-text.txt`
contains the original eight outcomes, eleven-section Planner handoff, human
approval (`approved, proceed`), implementation report, and first remediation
evidence. The current conversation additionally approves retaining the additive
staging launcher and amending ADRs 0012/0014 without external-action expansion.
The latest user instruction authorizes fixing R3 findings and repeating
independent review until ready for QA. This approval permits bounded iteration;
the report itself grants no additional authority.

The scope remains repository-owned single-host Linux Docker Compose staging,
one explicit application digest shared by API/worker, explicit dependency
digests, external secrets, read-only approved artifacts, local durable volumes,
Caddy HTTPS, health interfaces, and recovery guidance. No live deployment,
paid resources, DNS, credentials, promotion, API/security-policy changes,
worker/schema changes, or W8D4 smoke/rollback execution are authorized.

Coder's standalone R3-remediation report in this task identifies exactly four
changed subject files versus R3: staging launcher, its tests, env template, and
production-readiness guidance. It reports 26 new cases, a disposable replacement
for the repository-env test root, strict literal/allowlisted dotenv input,
canonical matching PostgreSQL URL, and preserved REV-001/002. Full-gate evidence
is recorded below and distinguished from Reviewer checks.

## Verdict

**CHANGES REQUIRED**

REV-003 and REV-004 are resolved, and REV-001/002 remain resolved. A newly
demonstrated startup incompatibility affects the accepted percent-encoded
PostgreSQL password path. Green Compose/driver checks do not cover the existing
Alembic configuration parser that runs before API startup.

## Findings

### VDDAI-REV-005 — MEDIUM — Accepted encoded database passwords fail migration startup

- Status: `OPEN`.
- Locations: `scripts/run_staging_compose.py:208-218`;
  `deploy/staging/staging.env.example:7-8`; integration boundary
  `alembic/env.py:11-12`.
- Evidence: the launcher accepts `POSTGRES_PASSWORD=synthetic:p@ss` and its
  canonical percent-encoded URL. The new template/runbook explicitly recommend
  percent encoding and the new Compose test accepts punctuation. API startup
  executes `alembic upgrade head` first. Existing Alembic code passes the URL
  unchanged to `config.set_main_option`, whose ConfigParser rejects percent
  escapes as invalid interpolation syntax. A safe diagnostic using the actual
  `alembic.config.Config('alembic.ini')` confirmed the URL is unset and that
  setting the accepted synthetic URL raises `ValueError` before any connection.
- Failure scenario: an operator follows the new encoding instructions with a
  generated password containing `:`, `@`, `/`, or similar characters. Validation
  and Compose render pass, but the API exits before migrating or starting;
  worker and Caddy cannot satisfy the API-health dependency.
- Impact: documented accepted staging configuration cannot start reproducibly.
  This is a configuration compatibility defect, not a requirement to change
  database persistence, authentication policy, or the existing migration code.
- Required action: within the approved staging-only scope, reject PostgreSQL
  password characters requiring percent encoding and document a URL-unreserved
  ASCII password subset, preserving strong randomly generated literal passwords.
  Keep matching internal URL/credential checks. Do not broaden this remedy into
  an Alembic runtime change without a separate scope decision.
- Closure verification: permanent rejected-encoded-password cases must fail
  before Compose; a supported synthetic password must survive Compose delivery,
  actual Alembic Config set/get, and SQLAlchemy/psycopg argument construction
  unchanged, without a database connection. Retain all R3 regressions and rerun
  focused, docs/formatting, and canonical gates with captured terminal status.

### Prior finding status

- `VDDAI-REV-001` — HIGH — `VERIFIED RESOLVED`: generated readiness still probes
  `/health` and `/health/model`; worker/Caddy still require API health. Source
  inspection and fresh focused suite confirm the wiring. This is not a live
  model-inference verification.
- `VDDAI-REV-002` — MEDIUM — `VERIFIED RESOLVED`: generated and command-line
  project name remain `vddai-staging`. Fresh actual Compose render with a
  conflicting ambient name confirms the fixed name.
- `VDDAI-REV-003` — HIGH — `VERIFIED RESOLVED`: literal printable ASCII checks
  reject quoting, interpolation, comments/escapes, duplicate keys, default and
  template JWT values before Compose. Real render confirms accepted synthetic
  JWT/PostgreSQL values are delivered unchanged. Required settings cannot be
  absent or empty. No application authentication policy was changed.
- `VDDAI-REV-004` — MEDIUM — `VERIFIED RESOLVED`: exact canonical URL equality
  enforces internal `postgres:5432`, matching bootstrap credentials/database,
  no query/fragment or alternate target. The env allowlist blocks libpq PG*
  routing overrides; fresh real-render/driver checks establish the effective
  host without opening a connection. REV-005 concerns a separate startup parser.

## Acceptance-criteria coverage

| Approved outcome | Implementation and verification evidence | Result |
|---|---|---|
| Reproducible provisioning/configuration | Versioned launcher/template, fixed project and digest checks; accepted password fails Alembic startup. | Incomplete: REV-005 |
| API/worker use approved immutable image identity | Shared digest, distinct commands, no source/build substitution; immutable/container tests pass. | Satisfied in reviewed scope |
| Configuration/secrets outside source control | External env-file restriction, literal allowlist/default rejection, non-secret template; focused tests and real render pass. | Satisfied |
| Durable dependencies handled appropriately | Internal PostgreSQL/Redis, matching internal DSN, stable named volumes, read-only artifact snapshot. | Satisfied; startup blocked for REV-005 input |
| HTTPS/stable endpoint planned | Caddyfile, validated FQDN, ports 80/443, documented operator prerequisites. | Satisfied as configuration; no live TLS claim |
| Authenticated behavior/health verifiable | Existing routes and model-readiness gate preserved; safe JWT delivery proven. | Interfaces preserved; REV-005 can block startup |
| Deployment/rollback/recovery documented | Worker-stop, backup and schema downgrade guidance preserved; encoded-password instructions are incompatible. | Requires REV-005 documentation correction |
| No production deployment/model promotion | No deployment workflow, registry mutation, model generation or external action added/performed. | Preserved |
| Human-approved additive launcher amendment | ADRs 0012/0014 and decisions index consistently permit separate staging invocation with W8D2 helper reuse. | Satisfied |

## Checks run

- Git branch, HEAD, merge base, staged/unstaged/untracked inventories and full
  subject reads completed. SHA-256 comparison with R3 confirms only the four
  authorized subject files differ. No generated artifact or actual secret file
  is included in the subject.
- `git diff --check`: passed.
- `.\.venv\Scripts\python.exe scripts/validate_docs.py`: passed before report
  creation (25 canonical documents, 68 Markdown files).
- Independent focused checks: **45 passed in 1.37 seconds**, exit 0, including
  actual Docker Compose config rendering with synthetic inputs. Exact command:

```powershell
@'
import subprocess, sys, tempfile
with tempfile.TemporaryDirectory(prefix='vddai-r4-review-') as base:
    result = subprocess.run([sys.executable, '-m', 'pytest', '-q',
        '--basetemp=' + base, 'app/tests/test_run_staging_compose.py',
        'app/tests/test_run_immutable_compose.py',
        'app/tests/test_container_contract.py'])
print('Disposable reviewer pytest directory cleaned.')
raise SystemExit(result.returncode)
'@ | .\.venv\Scripts\python.exe -
```

- Independent REV-005 diagnostic, executed through the pinned Python on stdin:

```python
from alembic.config import Config
from urllib.parse import quote
from scripts.run_staging_compose import validate_staging_settings
settings = dict(
    ENVIRONMENT='staging', POSTGRES_USER='review_user',
    POSTGRES_PASSWORD='synthetic:p@ss', POSTGRES_DB='review_db',
    REDIS_URL='redis://redis:6379/0', JWT_SECRET_KEY='synthetic-review-jwt',
    IMAGE_STORAGE_BACKEND='local', IMAGE_STORAGE_ROOT='uploads',
    MODEL_REGISTRY_PATH='artifacts/registry/model_registry.sqlite3',
    MODEL_ARTIFACT_ROOT='.')
settings['DATABASE_URL'] = ('postgresql+psycopg://review_user:'
    + quote(settings['POSTGRES_PASSWORD'], safe='') + '@postgres:5432/review_db')
validate_staging_settings(settings)
config = Config('alembic.ini')
assert not config.get_main_option('sqlalchemy.url')
try:
    config.set_main_option('sqlalchemy.url', settings['DATABASE_URL'])
except ValueError:
    print('Accepted staging URL fails Alembic configuration before connection')
else:
    raise AssertionError('Expected interpolation rejection')
```

The diagnostic confirmed the failure without printing the URL/exception value
or opening a connection. No diagnostic file was persisted.

### Supplied Coder verification evidence

Coder captured `powershell.exe -NoProfile -ExecutionPolicy Bypass -File
.\scripts\verify.ps1 -IncludeDockerConfig -IncludeFormatting` through a pinned
Python subprocess, setting `PYTEST_ADDOPTS` to an isolated TemporaryDirectory
basetemp. Result: **exit 0; 410 passed, 7 skipped in 66.02 seconds**. Dependency
versions/pip check, documentation, changed Python formatting, Alembic single
head `20260821_04`, and Docker configuration checks passed. Temporary resources
were cleaned. This is supplied Coder evidence, not an independent full-suite
Reviewer or QA run. It resolves the old missing terminal-output concern but
does not invalidate the independent REV-005 reproduction.

## Checks not run

- Full canonical gate was not duplicated by Reviewer; the fresh Coder result
  above is available. QA must independently obtain/classify its required gates.
- No service startup, GHCR pull/build/publication, live PostgreSQL connection,
  migration application, DNS/TLS issuance, deployed authentication/inference,
  rollback, or model promotion. External PostgreSQL test configuration was
  absent in the Coder gate; seven optional tests remained skipped.
- No live-staging/W8D4 acceptance claim is made. Those actions are excluded
  from the approved repository configuration work.

## Ordered remediation handoff

1. Coder: under the user's already granted fix/review iteration authorization,
   address `VDDAI-REV-005` only in `scripts/run_staging_compose.py`,
   `app/tests/test_run_staging_compose.py`, `deploy/staging/staging.env.example`,
   and necessary `docs/engineering/production-readiness.md` wording.
2. Reject incompatible encoded-password input before Compose. Keep canonical
   internal DSN, supported literal secrets, allowlisted env settings,
   REV-001/002 readiness/project identity, and W8D2 behavior unchanged.
3. Verify the complete accepted handoff through Compose, Alembic Config, and
   driver argument construction, with synthetic settings and no connections.
   Run focused tests and the complete canonical gate; capture exit status.
4. Return a standalone Coder report. Independent Reviewer writes R5, preserves
   IDs 001-005, and checks the whole resulting subject. QA is not yet eligible.
5. Do not alter old reports. No commit/push/merge, live deployment, secrets,
   infrastructure, data, or model action is authorized by this handoff.

## Residual risks, assumptions, and subject identity

Approved single-host/non-HA storage, manual backups, operator-provisioned
artifact identity, domain/GHCR access and host capacity remain deployment
prerequisites. They are scope limitations, not acceptance of REV-005.

These SHA-256 values identify the reviewed non-audit delta. Unchanged tracked
files are identified by the base commit. Subsequent roles must compare bytes
as well as branch/HEAD; R5 is required after remediation.

| File | SHA-256 |
|---|---|
| `.gitignore` | `382f9240ede2be5b4f0d516441fe0482ad86ffed6afb8352a35fccd032f99aa2` |
| `app/tests/test_run_staging_compose.py` | `31fed1a0dfbc0c17c794cd58138844d0ec9cce86d932458ded06abd29eb171a0` |
| `deploy/staging/Caddyfile` | `8c3a9b18498a24326773a7eab992584d57ad3d773623e1848bb0435ee1879707` |
| `deploy/staging/staging.env.example` | `e7482bcf96f771b8a8700e0456ae80d41d503c9973b5d2a78c7068400599b8fa` |
| `docs/architecture/system-requirements.md` | `f70c6fb4381d14f859b62b64ac5bbeef787d5a1314705ddab6daaf75f0f36061` |
| `docs/catalog.yaml` | `81f1ce90eaaa8cdc06d78b52c92aa64a4ad5ac38403f0ec6f8695dd4014febb7` |
| `docs/decisions/0012-immutable-application-image-publication.md` | `d042a4efc9170057a01b91ab4529405d8a45ee669fe4c737d0478f1faf71db38` |
| `docs/decisions/0014-single-host-staging-environment.md` | `fb18d503c292ef7defc968689ed0ad33578302394d931d577edb9ef78bd66c94` |
| `docs/decisions/README.md` | `7747300a6e2ab1b51ee4091a18a185e9bb697240ee89fcfc5b54ed193181681b` |
| `docs/engineering/production-readiness.md` | `06dd7154dc0567231a0522797e4b3928e2d88a2bb8f066b5ace59a1a62030c78` |
| `readme.md` | `72cb019196fb2c8ae4a7ac71ebf6614580e08cc188bcdaf1645768400b4dcf80` |
| `scripts/run_staging_compose.py` | `246fc57e5b6319a6ba7b61c7c08b3ca73ab52ad55eff0ec1c4f5a5115d67508b` |

## Process-learning evidence

- Observation: effective Compose and driver validation missed an intermediate
  migration configuration parser used during the real API startup sequence.
- Evidence: `VDDAI-REV-005`; `alembic/env.py:11-12`; 45 passing focused checks
  alongside the separate ConfigParser failure reproduction.
- Impact: avoids delivering an accepted but non-starting staging configuration.
- Recurrence: repeated cross-component interpretation gap, distinct parser.
- Candidate improvement: cover every configuration consumer in startup-order
  regression checks using synthetic inputs; proposal only.
- Authority note: this evidence authorizes no skill or workflow change and does
  not expand the user's bounded remediation approval.
