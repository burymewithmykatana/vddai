# ADR 0016 — HS256 JWT Provider and Strict Dependency Audit

- Status: Accepted
- Date: 2026-11-28
- Supersedes: [ADR 0013](0013-temporary-ecdsa-audit-exception.md)

## Context

The dependency audit on PR #23 reported an advisory against `python-jose`
with no fixed release. That library also brought the `ecdsa` dependency
covered by the temporary audit exception. [Failed dependency audit](https://github.com/burymewithmykatana/vddai/actions/runs/46156779607/job/141015068345)

## Decision

Use the pinned PyJWT library for signing and verifying VDDAI's HS256 bearer
tokens. Token issuance retains the configured signing secret, expiration
interval, and `sub` and `exp` claims. Verification uses the configured key
and the fixed HS256 algorithm. Existing valid tokens remain interoperable.
An expired token is rejected from its exact expiration timestamp. Invalid
tokens follow the existing API authentication failure path.

Remove `python-jose`, `ecdsa`, `rsa`, and `pyasn1` from the dependency set.
The hosted dependency-audit job uses `pip-audit` in strict mode. Retire the
temporary ECDSA exception. The existing aggregate quality gate continues
to require a successful dependency audit.

## Consequences

The replacement needs no credential rotation or token reissuance. Existing
password hashing, active-user checks, and owner and administrator access
rules continue to apply. This is a dependency and verification change within
the existing authentication component.

## Verification

Verify legacy token interoperability, expiry, malformed claims and signatures,
the canonical suite, the strict PostgreSQL gate, and an application image
build. Audit the freshly installed pinned environment with the CI command.

```powershell
python -m pip_audit --local --strict
```
