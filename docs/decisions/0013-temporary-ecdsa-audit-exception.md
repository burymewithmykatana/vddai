# ADR 0013 — Temporary ECDSA Dependency-Audit Exception

- Status: Accepted
- Date: 2026-08-30
- Scope: W8D2 immutable application image publication

## Context

W8D2 adds a mandatory strict `pip-audit` check to the hosted quality gate. The
approved dependency remediation removes every fixable finding in the current
pinned environment by updating `cryptography`, `pyasn1`, and the pinned pip
bootstrap tool. The resulting audit still reports one unfixed advisory for
`ecdsa==0.19.2`:

| Audit ID | Advisory | Package | Status |
|---|---|---|---|
| `PYSEC-2026-1325` | `GHSA-wj6h-64fc-37mp` / `CVE-2024-23342` | `ecdsa==0.19.2` | No fixed version reported by the approved audit |

The package is a transitive dependency of the current JWT library. Removing or
replacing that library would change the authentication architecture and is not
part of W8D2.

## Decision

The CI audit remains strict. It ignores only the exact audit identifier
`PYSEC-2026-1325` through `--ignore-vuln PYSEC-2026-1325`; no package-wide or
global suppression is permitted. Every other audit finding remains a quality
gate failure.

VDDAI currently signs and verifies JWTs only with `HS256`, as fixed by
`app.core.security.ALGORITHM`. The application does not configure ES256,
ECDSA signing, EC-key generation, ECDH, or another runtime path that exercises
the affected ECDSA functionality. A regression test asserts that issued tokens
retain the `HS256` header and accepted decode path.

This exception expires immediately if the JWT algorithm or cryptographic
architecture changes. Such a change must eliminate this dependency risk before
approval; it may not rely on this exception.

## Consequences and Follow-up

- The current private GHCR publication gate has one documented, human-approved
  temporary exception while retaining strict audit behavior for every other
  advisory.
- W8D2 does not add ECDSA use, migrate `python-jose`, or alter authentication
  behavior.
- A separate security-hardening task must remove the `ecdsa` exposure,
  preferably through a reviewed authentication-library migration. That task
  requires its own plan and human approval.
- Paperclip was evaluated as an orchestration option and abandoned; it is not
  part of VDDAI.

## Verification

The approved audit command is:

```powershell
python -m pip_audit --local --strict --ignore-vuln PYSEC-2026-1325
```

It must report no remaining vulnerabilities. The Coder records the command
output with the W8D2 implementation evidence. On 2026-08-30, the remediated
local environment emitted:

```text
No known vulnerabilities found, 1 ignored
```

The one ignored finding is the exact approved `PYSEC-2026-1325` exception;
Reviewer, QA, and Documentation retain their normal independent roles.
