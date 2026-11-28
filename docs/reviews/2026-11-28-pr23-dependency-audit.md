# PR #23 dependency audit remediation review

## 1. Reviewed subject

Review `PR23-REV-2026-11-28-001`, 28 November 2026. Independent review of
the human-approved dependency remediation on
`codex/w9d5-local-pilot-soak`. The approved base and current `HEAD` are
`51f4f00fac6ec47acdb897e657ad80cbc6297e54`. The merge base with
`origin/master` is `1b9f6160883361bdb99298b256815197ccab8eba`. The
remediation has an empty committed range and an empty index. The worktree
delta contains ten tracked edits and the new ADR 0016.

| Reviewed file | SHA-256 |
| --- | --- |
| `.github/workflows/ci.yml` | `47d7c80f0873bc002a731ef9d4155a123fdd5581d6b236f7c8f31b49a80b3aac` |
| `app/core/security.py` | `7dc1d3c1981624e9682e56f0af38b66e9b3bf9c64e4a9b9bbee58f818f2bec2f` |
| `app/tests/test_security.py` | `cf37d8c0ebacb5fabbc269b6ef34b378a2a13ddac6759683622265646c21c2c7` |
| `docs/catalog.yaml` | `7f3c4669f740063b0ddecc85e0c087e4cd5a272164f7f36475e890aa0a12ad73` |
| `docs/decisions/0012-immutable-application-image-publication.md` | `2176dcacbc235f6e938087c0556ede54927125738dd52c5813d905b2ac60e786` |
| `docs/decisions/0013-temporary-ecdsa-audit-exception.md` | `e2c96e674b2430c0be7b0c834d91b202db8c76e2a4acb8373f1b3ba0690ca55e` |
| `docs/decisions/0016-hs256-jwt-provider-and-strict-audit.md` | `269757982a37a74a684674b20ba2e223ed27fd2c0831ec7489e5e8e492c81f85` |
| `docs/decisions/README.md` | `126704958c71219eea62a4e89d48e4130285fa7cc10fd7005283c6ca0b067dc4` |
| `docs/engineering/production-readiness.md` | `a36e649ed93c9e4095758d41b5aad7dbd7cc062235c699d908279ffb2cae2237` |
| `readme.md` | `d63c7fad2a2a6920a8bbbdb3a60972ae6766834c762c3f26d1144bd21fe4758f` |
| `requirements.txt` | `3c52de2adfe40d3a2512c6cd38610c07540508e86ed06334b772dc71a7a8b035` |

## 2. Contract and acceptance criteria

The approved task addresses the dependency audit failure on PR #23 at run
`46156779607`. It updates the approved exact pins, replaces `python-jose`
with PyJWT, and requires the strict hosted audit with zero exceptions. It
preserves the configured signing key and TTL, HS256, issued claim structure,
active-user and owner checks, and frozen ML behavior. The approved expiry
boundary rejects a token at its `exp` timestamp. The decision supersedes
ADR 0013. [Failed audit](https://github.com/burymewithmykatana/vddai/actions/runs/46156779607/job/141015068345) · [ADR 0016](../decisions/0016-hs256-jwt-provider-and-strict-audit.md) · [Superseded ADR 0013](../decisions/0013-temporary-ecdsa-audit-exception.md)

The review followed the root and application instructions and the independent
review workflow. The accepted image publication contract remains applicable
to the later hosted checks. [Root instructions](../../AGENTS.md) · [Application instructions](../../app/AGENTS.md) · [Lifecycle](../engineering/agent-workflow.md) · [ADR 0012](../decisions/0012-immutable-application-image-publication.md)

## 3. Verdict

**PASS** for the fingerprinted local remediation. This subject is eligible for
independent QA. The hosted Linux audit and aggregate quality gate remain
pending on the authorized PR update.

## 4. Findings

No actionable findings in the reviewed change set.

## 5. Acceptance coverage

| Criterion | Implementation and evidence |
| --- | --- |
| Install the approved exact versions and remove obsolete JWT dependencies | The decoded requirements diff contains the approved updates: AnyIO `4.14.2`, Black `26.10.1`, dnspython `2.9.2`, filelock `4.2.1`, httpcore2 and httpx2 `2.12.0`, Pillow `13.0.0`, and setuptools `84.1.0`. The pin for PyJWT is `2.15.1`. Reviewer independently verified the installed metadata and absence of `python-jose`, `ecdsa`, `rsa`, and `pyasn1` in the candidate environment. The paired HTTP libraries passed the existing workload deadline regressions. |
| Retire the temporary exception and require the strict hosted audit | The workflow invokes `python -m pip_audit --local --strict` with no advisory exclusions. The dependency audit still participates in the aggregate quality gate. The sealed clean Windows audit covered 94 installed dependencies and recorded zero findings and zero skips. |
| Keep existing bearer credentials compatible and reject invalid or expired credentials | Issuance still uses HS256, the configured key and TTL, string `sub` and numeric `exp`. The verifier pins HS256 and maps validation errors to the existing authentication failure. Reviewer independently checked both directions between `python-jose==3.5.0` and `PyJWT==2.15.1` with a fresh synthetic key, including acceptance one microsecond before `exp` and rejection at and after `exp`. The focused tests cover malformed tokens and claims, other keys and algorithms, non-authenticated and inactive clients, and owner-scoped prediction access. |
| Preserve the frozen model and image behavior with the Pillow update | The diff leaves preprocessing and scoring code, the package, registry, and database outside the change surface. Coder's checksum-verified baseline and candidate receipts differ only in the Pillow version across 12 synthetic and 46 normal-validation inputs. They report identical input, tensor and inference-outcome fingerprints for `mvtec-tile-resnet18-knn-fe64db2228370b2d` and identical registry checksums. The comparison used synthetic and normal-validation inputs. Reviewer verified the receipts and ran the prediction API suite, including the real inference path fixture. |
| Record the accepted JWT and audit boundary and validate packaging | ADR 0016 supersedes ADR 0013, with cross-references in the decisions index, catalog, production-readiness guide, image publication ADR and root README. Historical exception evidence remains available. The sealed Coder Linux image build and isolated authentication smoke passed. |

## 6. Checks executed and evidence

### Independent Reviewer checks

- Inspected the complete committed, staged, unstaged and untracked task range
  with `git --no-optional-locks`. Verified all eleven source hashes before
  and after the independent execution. `git diff --check` passed.
- Used `git --no-optional-locks archive --format=tar 51f4f00fac6ec47acdb897e657ad80cbc6297e54`
  with no inherited Git overrides, then overlaid the eleven fingerprinted
  paths into a disposable snapshot. Rebased a copy of the Python 3.14.3
  embedded runtime's module search onto the snapshot and verified the
  security module origin, exact installed packages, and pip `26.2`.
- An independently written `python -B -c` probe used each pinned JWT library
  in its own interpreter process. It verified both token directions, HS256,
  the exact emitted claim set and the configured default TTL. An injected
  clock verified the expiry boundary. Only outcome messages were retained.
- In the snapshot, `python -B -m pytest -q -p no:cacheprovider --tb=short --show-capture=no --basetemp <scratch>/pytest app/tests/test_security.py app/tests/test_auth.py app/tests/test_prediction_api.py app/tests/test_local_pilot_soak.py`
  passed **81 tests in 36.31 seconds**, zero skips. Scratch cleanup and the
  final source fingerprint check passed.
- Recomputed all fifteen SHA-256 digests in the Coder manifest, parsed
  `windows-audit.json` for counts, compared the baseline and candidate
  inference receipts, and verified the Linux image build ID and supplemental
  image audit error from their respective outputs.

### Sealed Coder checks inspected by Reviewer

The evidence directory is
`C:/Users/S.R.G/VDDAI-worktrees/evidence/pr23-audit-fix-b5148c`.
`SHA256SUMS.txt` has SHA-256
`17a94367aef6a6e0e6071c3caeec3558ddf9b27b31d4044c82218ddad038ed66`.

- `focused.txt` records 90 passing tests in 47.16 seconds.
- `canonical.txt` records `scripts/verify.ps1` with pinned Python and the
  formatting check. All 484 tests passed in 129.89 seconds with zero skips.
  Pins, package consistency, Alembic, documentation, and formatting passed.
  `unchanged-pr-range-formatting.txt` records the separate Week 9
  changed-range check with Black `26.10.1`.
- `strict-postgres.txt` records `python -B scripts/run_production_gate.py` on
  disposable PostgreSQL 16.15. All 172 selected tests passed in 65.88 seconds
  with 312 deselected and zero skips.
- `windows-audit-retry.txt` and `windows-audit.json` record the successful
  strict audit with `pip-audit==2.10.1` and no allowed advisories. The JSON
  hash is `8a2e664a36b158b39559aad6f268d587f90336d1a8f84c296b17cc89cfeb20d3`.
- `linux-image-build.txt` and `linux-image-auth.txt` record the successful
  Dockerfile build and isolated, no-network HS256 check on image ID
  `sha256:678e971d39482d1dd27d8afcc7fc9cd9a6d595f95cbf492f510808944fa1852a`.
- `legacy-token.txt` and `jwt-expiration-boundary.txt` record the Coder's
  synthetic two-way interoperability and frozen-clock verification.
  `baseline-inference.json` and `candidate-inference.json` report package
  manifest fingerprint
  `sha256:319e8c307f456b6d7f31c612970b56da0a51902b9e1901f7c00f838722290de4`,
  tensor fingerprint
  `a29930d35201f639bcd9f3e6400985afca092176a77b080edbe1ab6dd8a8723d`,
  and inference-outcome fingerprint
  `3ff45d1e7a52464dd42c9c3172ffc96685dd04be32e0a73e7cd1482e8475611c`.

## 7. Checks pending or outside this execution

- The hosted audit and aggregate quality gate await the authorized PR update.
  The pinned Windows audit, Linux image build, and Linux authentication smoke
  are local results.
- The supplemental in-image strict audit failed because the Dockerfile
  installs `torch==2.13.0+cpu` from the official CPU wheel index and the audit
  could not find that build on PyPI. The local receipt is
  `C:/Users/S.R.G/AppData/Local/Temp/vddai-pr23-audit-fix-b5148c/linux-audit.txt`,
  SHA-256 `cd461e32251f065e6d5cee7144acec04578a41581b978d982e14486cf636a35c`.
  The reviewed CI invocation retains strict audit of the standard pinned
  environment, with no exception for this supplemental check.
- Reviewer execution used disposable test data and synthetic keys. Full
  canonical, PostgreSQL, and model parity verification above are Coder runs.

## 8. Handoff

1. Proceed to independent QA against the shared base and all eleven exact
   file hashes. Verify bearer and authorization behavior, local audit
   evidence and the import compatibility of the changed dependencies.
2. Route QA success through Documentation. Verify hosted dependency audit
   and the aggregate quality gate on the authorized PR update.

## 9. Residual evidence and assumptions

The canonical suites emit PyJWT's recommended-length warnings for the
existing synthetic development placeholder. Independent interoperation used
a newly generated synthetic key. Installed audit results are point-in-time
evidence. The pinned production CPU Torch wheel remains outside the
successful audit evidence.

## Process-learning evidence

| Field | Record |
| --- | --- |
| Observation | The isolated Linux image uses a CPU-specific Torch wheel. Its package version and audit coverage differ from the standard CI-installed set. |
| Evidence | ADR 0016, `.github/workflows/ci.yml`, the sealed Windows audit, and `linux-audit.txt` for `PR23-REV-2026-11-28-001`. |
| Impact | A successful image build and a clean standard audit answer different verification questions. Keeping the receipts separate makes image coverage reviewable. |
| Recurrence | First observed in this review. |
| Candidate improvement | If runtime-image audit becomes a requirement, plan separate audit coverage for the exact installed CPU wheel. |
| Authority note | This observation does not authorize a skill or workflow change. |
