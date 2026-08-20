# A6 Graphify Repository Intelligence Integration Review

- Review ID: `VDDAI-A6-REVIEW-2026-08-20-01`
- Date: 2026-08-20
- Task: A6 — Integrate Graphify repository intelligence
- Review type: initial implementation review
- Verdict: `CHANGES REQUIRED`
- Base: `b025e1810d4f5753811b655a77c425a2c3997633`
- HEAD: `b025e1810d4f5753811b655a77c425a2c3997633`
- Branch: `codex/tooling/a6-graphify-repository-intelligence`
- Merge base: `b025e1810d4f5753811b655a77c425a2c3997633`
- Committed range: none; HEAD remains at the approved base
- Staged changes: none
- Reviewed subject: all modified tracked files and the three relevant untracked
  implementation files reported by `git status`, before this immutable report
  was added

## Contract Sources and Acceptance Criteria

The review used:

- the approved A6 task and its 12 acceptance criteria;
- the human-approved `$vddai-plan` handoff, including the revised
  purpose-specific authority contract and Coder handoff;
- the Coder implementation report for the exact working-tree subject;
- root [`AGENTS.md`](../../AGENTS.md) and
  [`app/AGENTS.md`](../../app/AGENTS.md);
- [`$vddai-review`](../../.agents/skills/vddai-review/SKILL.md);
- [`docs/README.md`](../README.md), [`docs/catalog.yaml`](../catalog.yaml),
  [`agent-workflow.md`](../engineering/agent-workflow.md), and
  [`repository-intelligence.md`](../engineering/repository-intelligence.md);
- the complete tracked diff, relevant untracked files, tests, ignore rules,
  verification script, generated state inventory, and direct repository source
  used to cross-check Graphify results.

The reviewed acceptance criteria were: successful local analysis; structural
graph and HTML/call-flow outputs; Planner, Reviewer, and QA query access;
derived-evidence agent contracts; repository identity and stale detection; no
manual generated-state maintenance; Documentation ownership of semantic
architecture; an explicit local/untracked artifact policy; blast-radius and
end-to-end demonstrations; preserved human workflow gates; no unrelated
runtime architecture or semantic-flow maintenance; and unchanged application
and ML behavior.

## Verdict

`CHANGES REQUIRED`

The core integration is bounded, purpose-specific, freshness-validated, and
well covered by focused and repository-wide checks. Two actionable defects
remain in the local query interface and its maintained operational guidance.
Neither affects production application or ML behavior, but both should be
closed before the A6 subject advances to QA.

## Findings

### VDDAI-REV-001 — MEDIUM — Non-positive query limits bypass bounded output

- Status: `OPEN`
- Location: `scripts/graphify_repository.py:420-427`
- Evidence: the wrapper declares `--depth` and `--budget` as unconstrained
  integers. Running
  `python scripts/graphify_repository.py affected classify_anomaly_score --depth -1`
  exited successfully, and running
  `python scripts/graphify_repository.py query "test" --budget -1` also exited
  successfully and emitted a response that Graphify estimated at approximately
  62,374 tokens. Graphify treated the negative budget as effectively unbounded
  rather than as an invalid cap.
- Failure scenario: an agent or operator supplies zero or a negative depth or
  budget, expecting validation or a bounded response. The wrapper forwards the
  invalid value and may produce misleading results or an extremely large
  response that consumes agent context and local resources.
- Why it matters: A6 exists to provide a safe, scoped repository-intelligence
  interface. Allowing an invalid cap to expand output undermines that bounded
  interface and makes agent use less predictable even though production
  runtime is unaffected.
- Required action: validate `--depth` and `--budget` as strictly positive
  integers in the tracked wrapper and fail before invoking Graphify when either
  value is non-positive. Add focused tests for zero and negative values and
  verify that no Graphify subprocess is invoked.
- Closure verification: run the new focused cases, the complete
  `app/tests/test_graphify_repository.py` suite, both invalid CLI examples, the
  targeted Black check, and the canonical repository gate. Invalid values must
  return nonzero with a concise error and no Graphify query output.

### VDDAI-REV-002 — LOW — Documented path example returns no path

- Status: `OPEN`
- Location: `docs/engineering/repository-intelligence.md:104-107`
- Evidence: the maintained scoped-query example
  `python scripts/graphify_repository.py path create_prediction process_prediction`
  exits zero but reports `No directed path found`. In the same fresh graph,
  verified examples such as
  `path test_authenticated_upload_worker_and_readback_use_real_inference_path process_next_prediction`
  return a one-hop extracted call path.
- Failure scenario: an operator follows the current documentation to learn or
  demonstrate the `path` interface and receives a no-result response because
  the example names do not match the repository's actual symbols.
- Why it matters: maintained operational commands should demonstrate the
  advertised behavior against the current repository rather than normalize a
  no-result example.
- Required action: replace the no-result path example with a current,
  repository-backed pair that returns a meaningful path, and retain direct
  source verification appropriate to the example.
- Closure verification: rebuild and validate the graph after remediation, run
  the documented path command successfully, inspect the referenced source
  directly, and rerun documentation validation.

## Acceptance-Criteria Coverage

| Criterion | Implementation and review evidence | Status |
|---|---|---|
| 1. Successful documented local analysis | Pinned `graphifyy==0.9.47`; real graph state validated for the reviewed working tree | Satisfied |
| 2. Graph and visualization outputs | Nonempty `graph.json`, `graph.html`, `GRAPH_REPORT.md`, and one call-flow HTML were inspected | Satisfied |
| 3. Planner, Reviewer, and QA query access | Tracked CLI exposes `affected`, `query`, `path`, and `explain`; role contracts describe optional use | Satisfied, subject to VDDAI-REV-001 and VDDAI-REV-002 |
| 4. Derived-evidence contracts | Root and role contracts consistently require purpose-specific, direct-source verification | Satisfied |
| 5. Revision identity and staleness | Sidecar binds root, HEAD, working state, version, graph checksum, output inventory, and `built_at_commit`; drift tests pass | Satisfied |
| 6. No manual graph maintenance | Generated directory is ignored; build and atomic sidecar writer own generated state | Satisfied |
| 7. Documentation owns semantic architecture | Documentation skill and engineering contract prohibit curating Graphify output into maintained docs | Satisfied |
| 8. Explicit output policy | `graphify-out/` is Git-ignored and Docker-excluded; `git ls-files graphify-out` is empty | Satisfied |
| 9. Two useful demonstrations | `classify_anomaly_score` blast radius and authenticated prediction-flow query were cross-checked against source | Satisfied |
| 10. Human workflow gates preserved | A5 workflow explicitly classifies Graphify as evidence within a role, not a stage, verdict, or approval | Satisfied |
| 11. No unrelated architecture or semantic-flow maintenance | No service, hook, watcher, shared graph, runtime framework, or semantic overlay was introduced | Satisfied |
| 12. Application and ML behavior unchanged | Diff is tooling, tests, instructions, ignore policy, and documentation only; canonical 266-test gate passes | Satisfied |

## Checks Run

- `python scripts/graphify_repository.py validate`
  - Passed before report creation; state matched the exact reviewed HEAD and
    working-tree fingerprint.
- `python scripts/graphify_repository.py path create_prediction process_prediction`
  - Exited zero but found no directed path; evidence for `VDDAI-REV-002`.
- `python scripts/graphify_repository.py explain classify_anomaly_score`
  - Passed and resolved the direct contract symbol and its extracted callers.
- `python scripts/graphify_repository.py path test_score_direction_and_strict_threshold_rule_are_frozen classify_anomaly_score`
  - Passed with a one-hop extracted call path.
- `python scripts/graphify_repository.py path test_authenticated_upload_worker_and_readback_use_real_inference_path process_next_prediction`
  - Passed with a one-hop extracted call path.
- `python scripts/graphify_repository.py affected classify_anomaly_score --depth -1`
  - Exited zero with no affected nodes; evidence for `VDDAI-REV-001`.
- `python scripts/graphify_repository.py query "test" --budget -1`
  - Exited zero and produced an approximately 62,374-token answer; evidence for
    `VDDAI-REV-001`.
- `git grep -n "create_prediction\|process_prediction\|PredictionResponse"`
  - Completed and was used only as direct-source evidence.
- `git diff --check`
  - Passed; Git reported only the existing Windows LF-to-CRLF normalization
    warning for `.dockerignore`.
- `git check-ignore -v graphify-out/graph.json graphify-out/graph.html graphify-out/GRAPH_REPORT.md graphify-out/vddai-graph-state.json`
  - All generated files matched the `graphify-out/` ignore rule.
- `git ls-files graphify-out`
  - Returned no tracked generated files.
- `.\scripts\verify.ps1 -IncludeDockerConfig`
  - Passed using the pinned `.venv`: exact dependency pins validated, `pip
    check` passed, documentation validation passed, 266 tests passed, and
    Compose configuration passed.
- `python -m black --check scripts/graphify_repository.py app/tests/test_graphify_repository.py`
  - Passed; both files would be left unchanged.

## Checks Not Run

- The Reviewer did not rerun `docker compose build`; Compose configuration was
  independently validated, and the Coder report records a successful API and
  worker image build after Docker Desktop became available. The findings do not
  affect Docker build behavior.
- Database migration, production inference, model artifact, and ML evaluation
  checks were not run because the reviewed diff changes none of those surfaces.
- No production, destructive, secret-bearing, model-promotion, commit, push,
  PR, or merge action was performed.

## Ordered Remediation Handoff

1. Address `VDDAI-REV-001` in
   `scripts/graphify_repository.py` and
   `app/tests/test_graphify_repository.py` by enforcing strictly positive
   `--depth` and `--budget` values before Graphify invocation. Run the finding's
   invalid-input closure checks and focused suite.
2. Address `VDDAI-REV-002` in
   `docs/engineering/repository-intelligence.md` by replacing the no-result
   path example with a verified current path and cross-checking its source.
3. Because remediation changes tracked source, tests, or documentation,
   regenerate the ignored Graphify outputs and state, rerun focused formatting
   and documentation checks, run
   `.\scripts\verify.ps1 -IncludeDockerConfig`, and return a complete Coder
   remediation report for the exact new subject.
4. Request independent re-review. Preserve both finding IDs; QA remains
   ineligible until a new immutable re-review verifies both findings resolved
   or records an explicitly human-accepted risk.

## Residual Risks and Assumptions

- Graphify remains an externally installed, pinned local tool. Exact-version,
  checksum, and repository-fingerprint checks bound but do not eliminate risk
  from defects inside Graphify itself.
- Graphify results may contain inferred relationships and remain derived
  structural evidence; direct repository sources govern behavioral
  conclusions.
- Adding this immutable review report changes the nonignored working tree and
  therefore makes the pre-report generated graph state stale by design. Future
  Graphify use must rebuild and validate state for the new subject.
- The report is the only repository write made by the Reviewer and remains
  uncommitted.
