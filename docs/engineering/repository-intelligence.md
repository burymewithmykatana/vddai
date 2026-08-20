# Repository Intelligence with Graphify

- Status: Current
- Last reviewed: 2026-08-20
- Scope: optional local structural discovery for VDDAI repository work

## Purpose and Authority

Graphify provides generated structural evidence about repository code. It can
help locate symbols, callers, dependencies, paths, and likely affected areas.
It is not a source of requirements or an executable contract, and it is never
required to plan, implement, review, test, document, or approve a change.

Authority is purpose-specific rather than a linear hierarchy:

| Purpose | Governing source |
|---|---|
| Operating constraints, safety, Git rules, and protected actions | Root and applicable nested `AGENTS.md` plus explicit human approvals |
| Task objective, scope, acceptance criteria, and intended change | Approved task and human-approved Planner handoff |
| Role entry, writes, responsibilities, reports, and verdicts | Applicable role skill |
| Lifecycle transitions, evidence freshness, backward routing, and merge gate | [`agent-workflow.md`](agent-workflow.md) |
| Current executable behavior | Source, tests, migrations, configuration, and scripts |
| Durable architecture decisions and frozen invariants | Accepted ADRs |
| Maintained semantic descriptions | Cataloged current documentation |
| Audit results for the exact current subject | Current subject-matched Reviewer and QA evidence |
| Structural discovery | A freshness-validated Graphify graph |
| Historical context | Archived material |

Authority for one purpose does not transfer to another. When sources governing
the same purpose conflict, stop and report the conflict. Never silently
reconcile executable behavior with an accepted ADR or frozen contract. Report
documentation drift against code and change only what the approved task
authorizes. If a task exceeds a durable decision, stop at the applicable human
approval boundary. If Graphify conflicts with direct repository evidence,
inspect the source and treat the Graphify result as stale, incomplete, inferred,
or wrong.

## Isolated Installation

Graphify is development tooling, not an application dependency. Do not add it
to `requirements.txt`, application images, or runtime services. Install the
pinned package into an isolated `uv` tool environment:

```powershell
uv tool install graphifyy==0.9.47
graphify --version
```

The wrapper accepts exactly Graphify `0.9.47` and disables Graphify query
logging with `GRAPHIFY_QUERY_LOG_DISABLE=1` for every invocation.

## Build and Validate

Build the code-only graph on demand from the repository root:

```powershell
python scripts/graphify_repository.py build
python scripts/graphify_repository.py validate
```

The wrapper runs the official code-only extraction, local clustering with
placeholder community labels, and call-flow export. The `--no-label` clustering
step performs no semantic naming or external model call. The wrapper requires
these nonempty generated files under ignored `graphify-out/`:

- `graph.json`;
- `graph.html`;
- `GRAPH_REPORT.md`;
- exactly one `*-callflow.html`; and
- `vddai-graph-state.json`, written atomically by the wrapper.

Do not manually edit or commit this directory. It is also excluded from Docker
build context. A build fingerprints the repository before and after Graphify;
if repository contents change during extraction, no fresh state is recorded.
A failed rebuild removes the usable state sidecar while preserving generated
diagnostic outputs, so an older graph cannot be mistaken for current evidence.

## Freshness Contract

The sidecar records its schema, absolute local repository root, full HEAD,
deterministic repository fingerprint, `graph.json` SHA-256, Graphify version,
generation timestamp, code-only mode, output inventory, and the graph's
`built_at_commit` identity.

The fingerprint covers HEAD, index and worktree status, and the normalized
paths and contents of every tracked or nonignored untracked file. Ignored
`graphify-out/` content cannot refresh its own identity. A dirty worktree is
valid only when its exact state is the state that was graphed. Any later
tracked, staged, unstaged, untracked, HEAD, version, output, graph checksum, or
state change makes the evidence unusable.

`validate` never regenerates evidence. Missing Graphify, a missing or malformed
state or output, a checksum mismatch, or stale identity returns nonzero and
directs the caller to inspect repository sources directly. Every query command
performs this validation first and supplies the explicit local graph path to
Graphify without shell execution.

## Scoped Queries

Use the tracked wrapper rather than invoking queries against an implicit or
global graph:

```powershell
python scripts/graphify_repository.py affected classify_anomaly_score --depth 3
python scripts/graphify_repository.py query --dfs "Trace the authenticated prediction flow from upload to persisted result"
python scripts/graphify_repository.py path test_authenticated_upload_worker_and_readback_use_real_inference_path process_next_prediction
python scripts/graphify_repository.py explain classify_anomaly_score
```

Planner may use fresh results for dependency, ownership, path, and blast-radius
discovery. Coder may use them to inspect the approved implementation area.
Reviewer may cross-check changed-component callers and dependents. QA may use
them to discover candidate affected flows and regression scope. Documentation
must use direct evidence for maintained semantic descriptions and must never
curate generated output into `docs/`.

All roles must verify material conclusions against direct source, tests,
configuration, migrations, ADRs, or current documentation as appropriate to
the conclusion's purpose. Graphify cannot prove behavior, satisfy an acceptance
criterion, replace a diff review, establish architecture, or authorize an
action.

## Demonstration Cross-Checks

For the anomaly-decision blast radius, compare generated discovery with direct
source evidence:

```powershell
python scripts/graphify_repository.py affected classify_anomaly_score --depth 3
git grep -n "classify_anomaly_score"
```

For the authenticated prediction flow, use a fresh graph to propose the path,
then inspect the corresponding API route, persistence model, worker lifecycle,
inference service, and contract tests directly:

```powershell
python scripts/graphify_repository.py query --dfs "Trace the authenticated prediction flow from upload to persisted result"
git grep -n "create_prediction\|process_prediction\|PredictionResponse"
```

## Explicitly Excluded Modes

The supported baseline is the local CLI and ignored local outputs. A local MCP
adapter may be used only as an optional interactive client after the same
wrapper validation and with an explicit graph path; it creates no repository
configuration or shared service contract.

Do not enable hooks, watchers, automatic regeneration, a shared HTTP server, a
global graph, semantic extraction, or generic `graphify codex install` or
`graphify agents install` behavior. Do not install Graphify-generated agent
instructions. If Graphify is unavailable or unsuitable, use ordinary direct
repository inspection with no loss of correctness.
