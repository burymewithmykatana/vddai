# VDDAI Agent Instructions

## Mission and Current Milestone

VDDAI is a production-oriented, domain-agnostic visual anomaly-detection
platform. The v0.1.0 objective is a credible production ML pilot that
demonstrates authenticated visual inspection, asynchronous inference,
reproducible ML pipelines, deterministic preprocessing, dataset and model
lineage, controlled model promotion, deployment and monitoring, and human
feedback.

The current reference use case is MVTec AD `tile`. Do not generalize the
runtime to multiple product categories unless a task explicitly requires it.

Week 5 production inference is complete. The current production path consumes
one explicitly configured, frozen model package and persists its score,
threshold, decision, latency, package ID, and full public-safe lineage. Week 6
adds experiment tracking, a model registry, and controlled model promotion.

For Week 6 changes:

- keep experiment recording, candidate registration, promotion, and serving
  resolution explicit and independently testable;
- preserve immutable dataset, code, parameter, metric, artifact, and model
  lineage;
- never select a production model by scanning for the newest artifact;
- preserve the frozen Week 5 inference contract unless the task explicitly
  authorizes a versioned contract change;
- agents may implement and test promotion machinery, but production promotion
  remains a human approval gate.

## Current Architecture

Application:

- FastAPI HTTP API with JWT authentication and owner-scoped prediction access;
- SQLAlchemy 2 persistence on PostgreSQL 16;
- Redis 7 infrastructure;
- database-backed asynchronous prediction queue;
- a separate polling prediction worker using row locks with `SKIP LOCKED`.

ML:

- deterministic shared image preprocessing;
- frozen torchvision ResNet-18 feature extraction;
- a training-only normal feature bank;
- exact Euclidean mean-k-nearest anomaly scoring;
- a normal-validation-only frozen threshold;
- a versioned production inference contract;
- a fail-closed model-package loader;
- persisted model and package lineage.

Infrastructure:

- Docker Compose;
- Alembic migrations;
- pytest;
- pinned Python dependencies in `requirements.txt`;
- generated datasets, evaluation outputs, feature banks, thresholds, and model
  weights kept outside Git through repository ignore rules.

Redis is part of the deployed stack, but the prediction queue is currently
database-backed. Do not describe or redesign it as a Redis queue without an
explicit architecture task.

## Repository Map

- `app/api/`: routes and request dependencies.
- `app/contracts/`: frozen cross-component inference behavior and types.
- `app/core/`: configuration, logging, and security.
- `app/db/`: database base, sessions, and initialization.
- `app/models/`: SQLAlchemy persistence models and lifecycle behavior.
- `app/schemas/`: API request and response schemas.
- `app/services/`: storage, preprocessing, package loading, and inference.
- `app/workers/`: asynchronous prediction worker.
- `app/tests/`: application, integration, migration, ML, and contract tests.
- `ml/`: offline data, feature, scoring, threshold, evaluation, and artifact
  generation pipelines.
- `alembic/`: persistent schema migrations.
- `docs/README.md`: documentation index, lifecycle rules, and agent routing.
- `docs/catalog.yaml`: machine-readable inventory of current maintained docs.
- `docs/product/`: product boundary, discovery, offer, markets, and measures.
- `docs/architecture/`: current system requirements and architecture boundaries.
- `docs/engineering/`: current cross-component engineering contracts.
- `docs/decisions/`: accepted Architecture Decision Records (ADRs).
- `docs/reviews/`: immutable review and remediation evidence.
- `docs/archive/`: historical context that is not a current requirement.
- `scripts/`: current operational and data-acquisition utilities.
- `artifacts/`: local or generated ML outputs. Do not add generated binaries or
  run outputs to Git unless the task explicitly requires a reviewed fixture.

Some legacy artifact files are already tracked. Do not remove, replace, or use
them as a precedent for committing new generated artifacts unless requested.

## Source of Truth and Change Scope

Before editing, read the task, the relevant implementation and tests, and any
applicable ADRs. Treat executable contracts and accepted ADRs as authoritative
for frozen behavior. If documentation and code disagree, report the conflict;
do not silently choose the more convenient interpretation.

Start documentation discovery at `docs/README.md` and use `docs/catalog.yaml`
to identify current sources. Review reports are audit evidence, and archived
documents are historical only; neither overrides current code, tests, accepted
ADRs, or cataloged current documentation.

When a task defines `IN SCOPE`, `OUT OF SCOPE`, `MUST PRESERVE`, or
`ACCEPTANCE CRITERIA`, those sections are authoritative. Implement the smallest
coherent change that satisfies them. Report useful out-of-scope improvements
separately instead of implementing them.

Do not perform unrelated refactors. Do not introduce infrastructure,
frameworks, abstractions, or services unless they solve a concrete v0.1.0
requirement. Do not split the application into microservices before v0.1.0
without an approved architecture decision.

## Repository Intelligence

Graphify is optional, local, generated repository intelligence for structural
discovery. Its authority is purpose-specific: a fresh Graphify graph may help
locate dependencies, callers, paths, and affected components, but it does not
define requirements, executable behavior, architecture decisions, role
responsibilities, workflow gates, or approval authority. Verify every material
Graphify conclusion against direct repository sources before acting on it.

Use only a graph that passes `python scripts/graphify_repository.py validate`
for the exact current HEAD and working-tree fingerprint. If Graphify is absent,
invalid, stale, incomplete, or conflicts with direct repository evidence, say
so and fall back to direct repository inspection. Graphify is never required
for correctness, review, QA, documentation, or task completion.

Do not manually edit `graphify-out/`, commit its generated contents, install
Graphify-generated agent instructions, enable Graphify hooks or watchers, or
create a shared Graphify service. Repository agents must not depend on
Graphify-generated agent instructions for their operating contract.

## Engineering Principles

In order of priority, prefer:

1. deterministic behavior;
2. explicit, versioned contracts;
3. fail-closed validation;
4. reproducibility;
5. traceable lineage;
6. small, reviewable changes;
7. testable boundaries;
8. backward-compatible evolution where reasonable.

Follow existing repository patterns before adding a new pattern. Add or update
regression tests whenever behavior changes. Record a new ADR when a change
alters a durable architecture boundary or invariant.

## ML Invariants

These rules are mandatory.

### Dataset integrity

- Training data may fit feature banks or train models.
- Validation data may select models, hyperparameters, or thresholds.
- Official test data is for final evaluation only.
- Never tune preprocessing, a model, a hyperparameter, a scorer, or a threshold
  against official-test results or error cases.

### Preprocessing and serving consistency

Offline and online inference must preserve the same shared preprocessing
contract. Do not silently change color conversion, EXIF handling, resize/crop
behavior, tensor shape/layout, dtype, numeric range, model-owned normalization,
or schema identifiers.

An intentional preprocessing-contract change requires an explicit version
change, regression tests, affected artifact regeneration, and documented
compatibility consequences.

### Model and experiment lineage

Never silently discard, infer, or fabricate dataset versions or fingerprints,
code revisions, preprocessing versions, extractor identity, feature dimensions,
feature-bank lineage, scorer configuration, thresholds, artifact checksums,
package identifiers, schema versions, parameters, or evaluation metrics.

Production inference must identify the exact promoted package and its required
dependencies. Week 6 experiment and registry records must remain auditable and
must not weaken the Week 5 serving lineage.

### Artifact validation

Production serving must fail closed when required artifacts are absent,
malformed, checksum-invalid, schema-incompatible, lineage-incomplete,
test-derived where forbidden, or dimensionally incompatible. Do not add a mock,
default-threshold, automatic-regeneration, random-weight, network-download, or
"latest artifact" fallback to production serving.

### Prediction semantics

Higher anomaly scores mean more anomalous. The frozen decision rule is:

```text
score > threshold  -> anomalous
score <= threshold -> normal
```

Equality is normal. Do not change the score direction or equality semantics
without explicitly versioning the inference contract and updating its tests
and compatibility documentation.

## Database Rules

All persistent schema changes must use Alembic. For every migration:

- inspect the current Alembic head and existing schema behavior;
- test upgrade from the current head;
- test downgrade where practical;
- preserve existing data unless destructive behavior was explicitly approved;
- update SQLAlchemy models, schemas, lifecycle rules, and tests consistently;
- report data-loss and compatibility risks.

Do not modify production persistence semantics solely to simplify tests. Keep
the repository's existing timezone-naive UTC persistence convention unless a
task explicitly includes a migration of that contract.

## API and Security Rules

Authentication, active-user checks, ownership boundaries, and administrator
behavior must remain enforced. Do not expose secrets, password hashes, internal
filesystem paths, detailed internal exceptions, or private model artifacts
through public responses.

When modifying a public response contract, preserve backward compatibility
unless explicitly authorized, and update schemas, tests, and documentation.
Continue returning non-disclosing not-found behavior for unauthorized access
where that is the existing endpoint contract.

## Worker Rules

Preserve a valid prediction lifecycle. A prediction must not silently remain
in an invalid intermediate state. Worker failures must roll back failed
transactions, attempt to persist a safe terminal failure, retain actionable
internal diagnostics, and expose only the stable safe failure code to clients.

Concurrent workers must not process the same queued prediction simultaneously.
Do not weaken the current PostgreSQL locking and lifecycle guarantees while
adding Week 6 package resolution.

## Verification

Use the repository's pinned environment. Run focused tests while developing,
then run the applicable complete checks before declaring a task complete.

The canonical default gate is:

```powershell
.\scripts\verify.ps1
```

It validates installed dependencies, documentation, the single-head Alembic
revision graph, and the complete test suite. Use
`.\scripts\verify.ps1 -IncludeDockerConfig` when Compose configuration is in
scope. Formatting remains an explicit check because the current repository has
pre-existing Black baseline drift; do not hide that drift or reformat unrelated
files as part of another task. `-IncludeFormatting` checks only staged,
unstaged, and untracked Python files locally; CI supplies an explicit base/head
range and checks every Python file added or changed by that range.

The canonical gate also runs:

```powershell
python scripts/validate_docs.py
```

Run it directly while reorganizing or editing documentation. It enforces the
documentation root taxonomy, catalog coverage, non-empty documents, kebab-case
filenames, category indexes, archive banners, and local-link integrity.

For normal Python changes:

```powershell
python -m pip check
python -m pytest -q
```

For formatting-relevant Python changes:

```powershell
python scripts/validate_python_formatting.py
```

For database changes, configure a reachable test/development database first,
then run:

```powershell
alembic upgrade head
python -m pytest -q
```

Exercise the relevant downgrade path when practical. Never target a production
database for agent verification.

When Docker behavior changes, validate the Compose definition and the affected
container path. The current repository commands are:

```powershell
docker compose config --quiet
docker compose up --build -d
docker compose ps
docker compose exec api python -m pytest -q
```

Use the health checks documented in `readme.md`. Do not run
`docker compose down -v` unless deletion of the local development volume is
explicitly authorized.

For documentation-only or instruction-only changes, inspect the rendered
content, validate every referenced path and command against the repository,
and inspect the complete Git diff. Run code tests when the documentation
changes executable expectations or when task acceptance criteria require them.

Never claim that a command passed unless it was actually executed successfully.
If a check cannot run, report the exact blocker and distinguish it from a test
failure.

## Definition of Done

A task is complete only when:

- the requested behavior and acceptance criteria are satisfied;
- appropriate tests were added or updated for behavior changes;
- all applicable verification passes, or blockers are reported accurately;
- the complete diff contains no unrelated changes;
- public behavior and architecture documentation are updated when needed;
- durable architecture decisions are recorded when appropriate;
- assumptions, known limitations, and unresolved risks are reported.

Before handoff, inspect the diff and report changed files, checks executed,
acceptance-criteria coverage, and remaining risks.

## Git Rules

- Never push directly to `master`.
- Use one branch or worktree per independently reviewable task.
- Keep commits logically focused.
- Do not rewrite shared history.
- Do not push unless the task explicitly permits pushing.
- Do not merge automatically.
- A successful implementation is not approval to merge.

Prefer descriptive branch names such as `feat/w6-experiment-tracking`,
`feat/w6-model-registry`, `test/w6-inference-integration`, or
`fix/<short-description>`.

## Human Approval Required

Stop and request human approval before:

- merging into `master`;
- deploying to production;
- deleting persistent data or local database volumes;
- applying a destructive migration;
- changing authentication or security policy;
- changing the frozen ML evaluation protocol;
- promoting or rolling back a production model;
- changing fundamental architecture;
- rotating or modifying real secrets.

Prepare the proposed change and its evidence, then request review. Production
model promotion must be an explicit, auditable human action even after Week 6
promotion tooling exists.
