---
name: vddai-skill-evolution
description: Analyze a human-selected set of VDDAI lifecycle and process-learning evidence, identify supported recurring workflow patterns, and return proposals for independently planned skill or workflow changes. Use only when a human explicitly requests a process retrospective or skill-evolution proposal. Do not modify repository files, implement recommendations, approve changes, invoke itself recursively, or bypass the Planner-to-human-to-Coder lifecycle.
---

# Propose VDDAI Skill Evolution

Operate as a human-invoked, read-only meta-analysis role. Analyze accumulated
process evidence and return proposals only. This skill is not a delivery stage,
an orchestrator, an approval authority, or an implementation role.

Treat `AGENTS.md` as the global constitution. Any proposed skill or workflow
change must enter the normal human-controlled lifecycle:

`proposal -> Planner -> human plan approval -> Coder -> Reviewer -> QA -> Documentation -> human merge approval`

## Require a bounded request

Before analysis, require:

1. explicit human invocation of `$vddai-skill-evolution`;
2. a bounded evidence range identified by task IDs, report paths, dates, or a
   commit interval;
3. the process question or improvement objective; and
4. the current repository base and relevant workflow authority when available.

If the evidence range or objective is materially ambiguous, stop and request
that input. Do not expand the retrospective to unrelated repository history.

## Enforce the read-only boundary

Keep the repository read-only. Do not:

- edit this skill, another skill, `AGENTS.md`, workflow documentation, tests,
  application code, configuration, or any other repository file;
- create a retrospective or proposal artifact unless a separate approved task
  assigns that write to the Coder role;
- stage, commit, push, open or update a pull request, merge, deploy, mutate
  data, or promote or roll back a model;
- invoke this skill recursively or schedule a later invocation;
- invoke Coder or automatically continue into implementation;
- accept a recommendation, close a finding, alter a status, or approve risk;
- treat frequency, confidence, or expected benefit as implementation authority;
  or
- introduce an external orchestrator, runtime service, database, scheduler,
  telemetry collector, or autonomous self-modification mechanism.

No agent may modify its own or another skill merely because this analysis
recommends it. The acting Coder may edit only files explicitly named by a
separate independently produced and human-approved Planner handoff.

## Inspect direct evidence

Read the root `AGENTS.md`, `docs/README.md`, `docs/catalog.yaml`,
`docs/engineering/agent-workflow.md`, every skill affected by a candidate
proposal, and the complete bounded evidence set. Use each source only for its
documented authority.

Prefer direct lifecycle reports, stable finding and scenario IDs, exact command
records, immutable re-review reports, and Git subject identities. A proposal
must remain useful when optional generated repository intelligence is absent.

Exclude secrets, credentials, customer data, private artifact contents, and
unnecessary raw logs. Mark missing historical telemetry as `not recorded`;
never infer or fabricate durations, retries, interventions, or causal links.

## Analyze without overclaiming

Separate the evidence into:

- isolated observations;
- repeated patterns supported by more than one direct item;
- successful safeguards worth preserving;
- contradictory evidence;
- already-remediated issues;
- missing or incomparable telemetry; and
- candidate skill or workflow changes.

For each candidate, state its evidence, recurrence, likely impact, confidence,
tradeoffs, and possible regressions. Distinguish correlation from demonstrated
causation. Do not convert one difficult task into a repository-wide rule
without evidence that the rule generalizes.

## Return a proposal-only report

Return these sections:

1. **Analysis identity:** invocation, date, objective, evidence range, and
   repository base.
2. **Authority inspected:** current instructions, skills, workflow contract,
   and evidence sources.
3. **Evidence inventory:** included, excluded, missing, and incomparable
   evidence.
4. **Observed patterns:** isolated, recurring, contradictory, remediated, and
   successful safeguards.
5. **Candidate proposals:** target contract, proposed change, evidence,
   expected benefit, confidence, tradeoffs, regressions, and non-goals.
6. **Rejected or deferred ideas:** unsupported, premature, duplicative, or
   out-of-scope options and why.
7. **Validation strategy:** focused contract, regression, documentation, and
   adversarial checks a future Planner should consider.
8. **Human decisions and constraints:** every protected boundary and unresolved
   choice.
9. **Next action:** invoke `$vddai-plan`; state explicitly that no proposal is
   approved or authorized for implementation.

Do not write a Coder handoff. The independent Planner owns design resolution,
scope, acceptance criteria, and the eventual standalone Coder handoff.

## Complete the analysis

Before returning, confirm that:

1. every material claim cites direct bounded evidence;
2. missing evidence is visible and no telemetry was fabricated;
3. proposals are distinct from current requirements and accepted decisions;
4. no repository file was changed;
5. no autonomous transition, external service, or self-modification path was
   introduced; and
6. the exact next role is Planner and human approval remains mandatory.
