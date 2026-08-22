from __future__ import annotations

import os
import sys
from collections.abc import Mapping

import pytest

POSTGRES_DATABASE_URL_ENV = "VDDAI_TEST_POSTGRES_DATABASE_URL"


class RequiredPostgresEvidencePlugin:
    """Fail the W7D4 run when required PostgreSQL evidence is absent or skipped."""

    def __init__(self) -> None:
        self.required_nodeids: set[str] = set()
        self.observed_nodeids: set[str] = set()
        self.skipped_nodeids: set[str] = set()

    def pytest_collection_modifyitems(self, items: list[pytest.Item]) -> None:
        self.required_nodeids = {
            item.nodeid
            for item in items
            if item.get_closest_marker("w7_production_gate") is not None
            and item.get_closest_marker("postgres_integration") is not None
        }

    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        if report.nodeid not in self.required_nodeids:
            return
        self.observed_nodeids.add(report.nodeid)
        if report.skipped:
            self.skipped_nodeids.add(report.nodeid)

    def blocked_reasons(self) -> list[str]:
        reasons: list[str] = []
        if not self.required_nodeids:
            reasons.append("no required PostgreSQL integration tests were collected")
        missing = self.required_nodeids - self.observed_nodeids
        if missing:
            reasons.append(
                "required PostgreSQL tests did not run: " + ", ".join(sorted(missing))
            )
        if self.skipped_nodeids:
            reasons.append(
                "required PostgreSQL tests skipped: "
                + ", ".join(sorted(self.skipped_nodeids))
            )
        return reasons

    def pytest_sessionfinish(
        self,
        session: pytest.Session,
        exitstatus: int | pytest.ExitCode,
    ) -> None:
        del exitstatus
        reasons = self.blocked_reasons()
        if not reasons:
            return
        terminal_reporter = session.config.pluginmanager.get_plugin("terminalreporter")
        message = "W7D4 production gate BLOCKED: " + "; ".join(reasons)
        if terminal_reporter is not None:
            terminal_reporter.write_sep("=", message, red=True)
        else:
            print(message, file=sys.stderr)
        if session.exitstatus == pytest.ExitCode.OK:
            session.exitstatus = pytest.ExitCode.TESTS_FAILED


def run_production_gate(
    *,
    environ: Mapping[str, str] | None = None,
) -> int:
    effective_environment = os.environ if environ is None else environ
    database_url = effective_environment.get(POSTGRES_DATABASE_URL_ENV, "")
    if not database_url.strip():
        print(
            "W7D4 production gate BLOCKED: "
            f"{POSTGRES_DATABASE_URL_ENV} must identify an explicitly "
            "disposable PostgreSQL 16 database.",
            file=sys.stderr,
        )
        return int(pytest.ExitCode.TESTS_FAILED)

    plugin = RequiredPostgresEvidencePlugin()
    return int(
        pytest.main(
            ["-q", "-m", "w7_production_gate"],
            plugins=[plugin],
        )
    )


def main() -> None:
    raise SystemExit(run_production_gate())


if __name__ == "__main__":
    main()
