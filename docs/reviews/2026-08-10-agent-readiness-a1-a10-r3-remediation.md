# Agent-Readiness A1-A10 R3 Remediation Record

- Remediation date: 2026-08-10
- Source review: `docs/reviews/2026-08-10-agent-readiness-a1-a10-r3.md`
- Source verdict: `CHANGES REQUIRED`
- Findings addressed: `VDDAI-REV-001`, `VDDAI-REV-007`
- Repository base: `origin/master` at `49a5b58c018602adfcf394c336528aec2cc13810`
- Branch: `chore/agent-readiness-a1-a10`
- Commit, push, merge, deployment, and model promotion: not performed

## VDDAI-REV-001 Disposition

- Severity: `MEDIUM`
- Remediation status: `ADDRESSED — INDEPENDENT CLOSURE REVIEW REQUIRED`

The recurring Windows/WSL line-ending discrepancy is addressed with an explicit
repository policy in `.gitattributes`:

- automatic text detection remains enabled;
- repository instructions, Markdown, Python, PowerShell, YAML, JSON, common
  configuration files, the Dockerfile, `.gitignore`, and `.gitattributes` use
  LF in the repository;
- the UTF-16 `requirements.txt` file is not forcibly treated as UTF-8 text.

The two newly visible CRLF contract sources identified by R3—ADR 0002 and the
Week 5 task document—were mechanically normalized to LF without changing their
content beyond the separately documented ADR amendment. `.gitignore` was also
normalized to LF while preserving its substantive two-line removal of the
broad `docs/` rule.

Fresh evidence:

- Windows Git and WSL Git report the same working-tree scope;
- both report only `.gitignore` as a modified tracked file;
- both report the tracked diff as two deletions and no unrelated tracked-file
  churn;
- both `git diff --check` paths pass;
- every ordinary untracked task file contains zero CRLF sequences.

The explicit policy prevents different agent hosts from recreating the prior
49-file line-ending-only patch.

## VDDAI-REV-007 Disposition

- Severity: `MEDIUM`
- Remediation status: `ADDRESSED — INDEPENDENT CLOSURE REVIEW REQUIRED`
- Changed file:
  `docs/decisions/0002-anomaly-baseline-and-pytorch-data-contract.md`

ADR 0002 remains accepted for its baseline choice, split boundaries, threshold
policy, and lineage intent. It is now marked as amended on 2026-08-10 and
explicitly records that later active contracts supersede two implementation
details:

- dataset samples and DataLoader batches remain in `[0, 1]`, while
  `ResNet18FeatureExtractor` owns exactly-once ImageNet normalization;
- the training loader uses deterministic seeded shuffling, while validation and
  official-test loaders preserve manifest order.

The ADR's tensor, determinism, consequences, and verification sections now
match `ml/data/torch_dataset.py`, `ml/data/torch_dataloader.py`,
`ml/feature_extractor.py`, ADR 0003, `ml/AGENTS.md`, the README, and
`docs/data_to_model_pipeline.md`. Historical context was preserved; executable
contracts were not changed to match stale text.

Focused checks confirm the accepted ADR no longer assigns normalization to the
PyTorch adapter, says tensors leave `[0, 1]`, or globally disables DataLoader
shuffling.

## Fresh Post-R3 Verification

The following checks ran after both R3 remediations:

| Check | Result |
|---|---|
| Windows Git status, stat, numstat, and diff check | Narrow and passed |
| WSL Git status, stat, numstat, and diff check | Matches Windows and passed |
| CRLF scan of every ordinary untracked task file | Zero CRLF sequences |
| ADR 0002 obsolete/current claim checks | Passed |
| `scripts/bootstrap.ps1 -PythonCommand .\.venv\Scripts\python.exe -CheckOnly` | Passed |
| Python version | `3.14.3` |
| pip version | `26.1.2` |
| Exact requirements pins | All 73 validated |
| `pip check` | No broken requirements |
| `python -m alembic heads` | One head: `20260803_02` |
| `scripts/verify.ps1 -IncludeDockerConfig` | Passed |
| Full pytest suite | 208 passed |
| Docker Compose configuration | Passed |

Formatting was not included because the repository documents pre-existing
Black baseline drift and no Python implementation file changed.

## Placeholder Documentation Decision

The four zero-byte documentation files exposed by removal of the broad docs
ignore rule will be retained as intentional, visible placeholders in the final
agent-readiness commit rather than deleted or re-ignored:

- `docs/architecture/system_requirement.md`;
- `docs/product/customer_discovery.md`;
- `docs/product/problem_statement.md`;
- `docs/product/success_metrics.md`.

They make no architectural claims. Keeping them visible ensures future content
is not silently excluded from Git. Filling them is outside the A1-A10 scope.

## Remaining Documented Risks

- The A1-A10 mapping remains reconstructed from the durable deliverables and
  review chain rather than a separate original specification file. The review
  reports preserve the mapping used for acceptance.
- Hosted CI evidence cannot exist until the branch is pushed and a pull request
  is opened. Local commands corresponding to the workflow are green.

Neither item blocks a local commit after an independent closure verdict.

## Final Review Handoff

Run a fresh independent closure review and write:

`docs/reviews/2026-08-10-agent-readiness-a1-a10-r4.md`

Preserve IDs `VDDAI-REV-001` through `VDDAI-REV-007`, verify the complete
workspace in both Windows and WSL Git views where available, and issue the final
verdict. Do not modify implementation, remediation, or prior review files.
