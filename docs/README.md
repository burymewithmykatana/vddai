# VDDAI Documentation

This directory is the entry point for product, architecture, engineering, and
delivery knowledge. Start here before treating an individual document as a
current requirement.

## Source-of-Truth Order

Use this authority order. If executable contracts and an accepted ADR disagree,
stop and report the conflict rather than silently selecting either one:

1. executable contracts, migrations, and tests together with accepted
   Architecture Decision Records under `decisions/`;
2. current architecture and engineering documents;
3. current product documents;
4. review reports as audit evidence;
5. archived documents as historical context only.

Repository-wide agent rules remain in [`../AGENTS.md`](../AGENTS.md). The
machine-readable document inventory is [`catalog.yaml`](catalog.yaml).

## Documentation Map

| Area | Purpose | Start here |
|---|---|---|
| Product | Customer problem, product boundary, pilot, markets, and success measures | [`product/README.md`](product/README.md) |
| Architecture | Current system requirements and architecture boundaries | [`architecture/README.md`](architecture/README.md) |
| Engineering | Current data, ML, serving, and operational contracts | [`engineering/README.md`](engineering/README.md) |
| Decisions | Accepted and superseded durable decisions | [`decisions/README.md`](decisions/README.md) |
| Reviews | Immutable review and remediation evidence | [`reviews/README.md`](reviews/README.md) |
| Archive | Historical snapshots that are not current instructions | [`archive/README.md`](archive/README.md) |

## Lifecycle Labels

- `current`: describes the present product or implementation.
- `draft`: structured working material that is not yet validated or approved.
- `accepted`: an active durable decision.
- `superseded`: retained for history but replaced by a later decision.
- `historical`: a point-in-time record that must not guide current changes.
- `audit`: immutable review or remediation evidence.

## Agent Workflow

Use the repository roles in this human-controlled order:

`approved task -> Planner -> human plan approval -> Coder -> Reviewer ->
remediation and re-review when required -> QA -> Documentation -> human merge
approval`

The maintained [`agent handoff and workflow contract`](engineering/agent-workflow.md)
defines required artifacts, eligibility and backward-routing conditions,
evidence freshness, optional-stage policy, and human gates. The role skills
remain authoritative for their own complete entry and output schemas.

- [`$vddai-plan`](../.agents/skills/vddai-plan/SKILL.md) turns an approved task
  into an implementation-ready plan without changing the repository.
- [`$vddai-code`](../.agents/skills/vddai-code/SKILL.md) implements only the
  human-approved handoff or explicitly approved remediation.
- [`$vddai-review`](../.agents/skills/vddai-review/SKILL.md) independently
  reviews the exact implementation range and owns immutable review findings.
- [`$vddai-qa`](../.agents/skills/vddai-qa/SKILL.md) independently verifies a
  current reviewed subject and returns criterion-specific behavioral evidence.
- [`$vddai-documentation`](../.agents/skills/vddai-documentation/SKILL.md)
  synchronizes durable documentation only after eligible Reviewer evidence and
  QA `PASS`, then leaves the proposed subject at the human merge gate.
- Use [`$vddai-ml-change`](../.agents/skills/vddai-ml-change/SKILL.md) alongside
  the applicable Planner or Coder role for ML, data, lineage, and artifact work.

For every role:

1. Read the root `AGENTS.md` and this index.
2. Use `catalog.yaml` to locate the current documents for the task area.
3. Read applicable ADRs before changing a durable boundary.
4. Never use `archive/` or a review report as a current requirement without
   confirming it against current code and accepted decisions.
5. Update the relevant document and catalog entry when a current contract or
   lifecycle status changes.
6. Run `python scripts/validate_docs.py`, then the repository verification gate.

Keep detailed technical truth in Git and repository documentation. Keep Notion
to roadmap status, priorities, and concise milestone outcomes. Keep change
history and review, CI, and merge evidence in GitHub pull requests and commits.

## Maintenance Rules

- Use lowercase kebab-case filenames; ADRs additionally use a four-digit prefix.
- Keep the `docs/` root limited to this index, `catalog.yaml`, and the documented
  category directories.
- Do not create empty placeholder documents.
- Do not silently rewrite review reports. Add a remediation or numbered
  re-review report instead.
- Move obsolete material to `archive/` with a historical status banner.
- Keep generated reports and runtime artifacts outside this maintained tree.
